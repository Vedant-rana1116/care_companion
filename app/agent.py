# ruff: noqa
import logging
import re
import json
from typing import Any, AsyncGenerator

from google.adk.agents import Agent, LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.tools import AgentTool, ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.workflow import Workflow, START, node
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.genai import types

from app.config import config

# Set up logging
logger = logging.getLogger("care_companion")
logging.basicConfig(level=logging.INFO)

# Define MCP Toolset connected to local stdio server
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "app.mcp_server"],
        )
    )
)

# Define custom tools
def request_report_approval(draft_text: str, tool_context: ToolContext) -> dict:
    """Queues a draft wellness report for the family, pending final approval from the user.
    
    Args:
        draft_text: The complete text content of the draft wellness report.
        
    Returns:
        A status dictionary confirming the draft was queued.
    """
    tool_context.state["draft_report"] = draft_text
    tool_context.state["needs_approval"] = True
    return {
        "status": "success",
        "message": "Wellness report draft has been successfully queued for approval."
    }

# Initialize sub-agents
medication_manager = LlmAgent(
    name="medication_manager",
    model=Gemini(model=config.model),
    instruction=(
        "You are the Medication Manager. You assist seniors with tracking their "
        "medication schedules, verifying correct dosages, checking safe timings, "
        "and warning of potential food-to-drug or drug-to-drug interactions. "
        "Use your mcp tools to lookup medication information (get_medication_info) "
        "or view/update schedules. Speak in a gentle, clear, and easy-to-understand tone. "
        "Always ask clarifying questions if you do not have enough context about their medications."
    ),
    description="Handles medication schedules, dosage tracking, safety checks, and interactions.",
    tools=[mcp_toolset],
)

exercise_guide = LlmAgent(
    name="exercise_guide",
    model=Gemini(model=config.model),
    instruction=(
        "You are the Exercise Guide. You specialize in guiding seniors through "
        "safe, gentle exercises like chair yoga, stretching, and light mobility movements. "
        "Use your mcp tools to view or update schedules. Always ask the user how they are feeling "
        "before suggesting workouts, prioritize safety, and remind them to stop immediately if they feel any discomfort or pain."
    ),
    description="Provides senior-friendly daily workout routines, stretching, and physical safety guidance.",
    tools=[mcp_toolset],
)

wellness_reporter = LlmAgent(
    name="wellness_reporter",
    model=Gemini(model=config.model),
    instruction=(
        "You are the Wellness Reporter. You help seniors compile logs of their mood, "
        "pain levels, sleep, and physical activity, and draft reports to share with "
        "their family or caregivers. Use your mcp tools to query schedules, log wellness metrics, "
        "and send notifications. When asked to draft or send a report, compile the details "
        "into a structured update, and call the request_report_approval tool to queue it for their review."
    ),
    description="Compiles vitals/logs and drafts weekly wellness updates for family and caregivers.",
    tools=[request_report_approval, mcp_toolset],
)

# Initialize main coordinator agent
orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(model=config.model),
    instruction=(
        "You are the CareCompanion Orchestrator, a daily health concierge for seniors. "
        "You help coordinate medication tracking, gentle exercise planning, and caregiver reports. "
        "You delegate specialized tasks to your sub-agents:\n"
        "- Call medication_manager for any medication schedule, dosage, or safety query.\n"
        "- Call exercise_guide for daily gentle exercise routines or mobility stretches.\n"
        "- Call wellness_reporter to compile health logs and draft updates for family.\n\n"
        "Communicate in a warm, respectful, and encouraging tone. Keep answers clear and simple."
    ),
    tools=[
        AgentTool(medication_manager),
        AgentTool(exercise_guide),
        AgentTool(wellness_reporter),
    ],
)

# --- Workflow Graph Nodes ---

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    # START node outputs types.Content. Convert to string for checking.
    user_text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        user_text = "".join([part.text for part in node_input.parts if part.text])
    elif isinstance(node_input, str):
        user_text = node_input

    # 1. PII Scrubbing
    cleaned_text = user_text
    
    # Phone numbers
    phone_pattern = r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
    cleaned_text = re.sub(phone_pattern, "[REDACTED_PHONE]", cleaned_text)
    
    # Emails
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    cleaned_text = re.sub(email_pattern, "[REDACTED_EMAIL]", cleaned_text)
    
    # SSN
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    cleaned_text = re.sub(ssn_pattern, "[REDACTED_SSN]", cleaned_text)
    
    scrubbed = (cleaned_text != user_text)
    
    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous", "override rules", "system prompt", "forget instructions", "developer mode"]
    detected_injection = any(kw in user_text.lower() for kw in injection_keywords)
    
    # Audit log
    audit_data = {
        "event": "security_scan",
        "session_id": ctx.session.id,
        "pii_scrubbed": scrubbed,
        "injection_detected": detected_injection,
    }
    
    if detected_injection:
        audit_data["severity"] = "CRITICAL"
        audit_data["action"] = "BLOCKED"
        logger.warning(json.dumps(audit_data))
        return Event(
            output="Security Alert: Potential prompt injection detected. Request blocked.",
            route="security_event"
        )
        
    audit_data["severity"] = "INFO"
    audit_data["action"] = "ALLOWED"
    logger.info(json.dumps(audit_data))
    
    # Pass clean text input downstream
    return Event(
        output=cleaned_text,
        route="default",
        state={"user_query": cleaned_text}
    )

def security_alert(node_input: str) -> Event:
    # Terminal node for blocked requests
    content = types.Content(role="model", parts=[types.Part.from_text(text=node_input)])
    return Event(content=content, output=node_input)

def orchestrator_router(ctx: Context, node_input: Any) -> Event:
    # Check if a report was queued for approval in state
    if ctx.state.get("needs_approval"):
        ctx.state["needs_approval"] = False
        draft = ctx.state.get("draft_report", "")
        return Event(output=draft, route="needs_approval")
        
    # Standard response output
    return Event(output=node_input, route="default")

async def human_approval_gate(ctx: Context, node_input: str) -> AsyncGenerator[Event, None]:
    if not ctx.resume_inputs or "report_approved" not in ctx.resume_inputs:
        prompt_msg = (
            f"Here is the draft report:\n\n{node_input}\n\n"
            "Do you approve sending this report to your family? (Please reply with 'yes' to approve, or anything else to reject)"
        )
        # Yield request input event to pause execution
        yield RequestInput(interrupt_id="report_approved", message=prompt_msg)
        return
        
    user_response = ctx.resume_inputs["report_approved"].strip().lower()
    if user_response == "yes" or "yes" in user_response:
        success_msg = f"✅ Weekly wellness report approved and shared with family:\n\n{node_input}"
        yield Event(output=success_msg, state={"draft_report": None})
    else:
        reject_msg = "❌ Report cancelled. Draft was not sent. Let me know if you want to revise it."
        yield Event(output=reject_msg, state={"draft_report": None})

def finalize_output(node_input: Any) -> Event:
    # Convert node_input to text
    text_content = ""
    if isinstance(node_input, types.Content):
        if node_input.parts:
            text_content = "".join([part.text for part in node_input.parts if part.text])
    elif isinstance(node_input, str):
        text_content = node_input
    else:
        text_content = str(node_input)
        
    content = types.Content(role="model", parts=[types.Part.from_text(text=text_content)])
    return Event(content=content, output=text_content)

# Define workflow edges
edges = [
    (START, security_checkpoint),
    (security_checkpoint, {
        "security_event": security_alert,
        "default": orchestrator
    }),
    (orchestrator, orchestrator_router),
    (orchestrator_router, {
        "needs_approval": human_approval_gate,
        "default": finalize_output
    }),
    (human_approval_gate, finalize_output),
]

root_agent = Workflow(
    name="care_companion_workflow",
    edges=edges,
    description="CareCompanion Workflow managing senior medication, exercise, and caregiver reporting.",
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
