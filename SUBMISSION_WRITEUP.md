# CareCompanion Submission Write-Up

## 1. Problem Statement
Many elderly individuals living independently face complex daily challenges managing their health. Specifically:
- **Medication Adherence**: Forgetting doses, mixing up schedules, or taking drugs at times that trigger dangerous side effects or food interactions.
- **Physical Inactivity & Safety**: A lack of structured, age-appropriate physical routines, combined with the risk of injury if workouts are too intense.
- **Caregiver Anxiety**: Family members and caregivers struggle to stay informed of wellness metrics, mood patterns, and adherence logs without constant manual prompting.

CareCompanion solves this by providing a unified, secure, conversational health concierge that coordinates schedules, encourages daily mobility, and automates structured reporting.

---

## 2. Solution Architecture

```
                       +----------------------------------+
                       |           User Prompt            |
                       +----------------------------------+
                                        |
                                        v
                       +----------------------------------+
                       |     Security Checkpoint Node     |
                       |  - Scrub PII (SSN, Phone, Email) |
                       |  - Detect prompt injection       |
                       +----------------------------------+
                           /                          \
            (Security Event)                          (Default Clean)
                 /                                      \
                v                                        v
+------------------------------+         +-------------------------------+
|     Security Alert Node      |         |  Orchestrator LlmAgent Node   |
| (Terminal - Blocked request) |         | - Delegates query to subagent |
+------------------------------+         +-------------------------------+
                                            /          |           \
                                      (AgentTool)  (AgentTool)  (AgentTool)
                                         /             |             \
                                        v              v              v
                                  +------------+ +------------+ +------------+
                                  | Medication | |  Exercise  | |  Wellness  |
                                  |  Manager   | |   Guide    | |  Reporter  |
                                  +------------+ +------------+ +------------+
                                         \             |             /
                                          +----(MCP Stdio Tools)----+
                                                       |
                                                       v
                                         +---------------------------+
                                         |    MCP Database Server    |
                                         | - Pharmacy info           |
                                         | - Daily schedules         |
                                         | - Metric logging          |
                                         +---------------------------+
                                                       |
                                                       v
                                         +---------------------------+
                                         |     Orchestrator Router   |
                                         +---------------------------+
                                            /                     \
                                    (Needs Approval)          (Default)
                                          /                         \
                                         v                           v
                        +-------------------------------+   +----------------+
                        |   Human Approval Gate Node    |   | Finalize Output|
                        | - Pause for RequestInput      |   +----------------+
                        | - Approved -> Send report     |
                        +-------------------------------+
```

---

## 3. Concepts Used

- **ADK 2.0 Graph-Based Workflow**: Defined in [agent.py](file:///c:/Users/Admin/Desktop/adk%20workspace/care-companion/app/agent.py), coordinating the control flow from security scans to orchestrator routing and human gates.
- **LlmAgents**:
  - `orchestrator` parses intentions and routes queries.
  - `medication_manager` focuses on dosage safety and timing.
  - `exercise_guide` designs stretches and gentle mobility.
  - `wellness_reporter` compiles metrics.
- **AgentTool**: Orchestrator delegates specialized reasoning to sub-agents (keeping the orchestrator in the loop).
- **Model Context Protocol (MCP)**: Implemented in [mcp_server.py](file:///c:/Users/Admin/Desktop/adk%20workspace/care-companion/app/mcp_server.py), providing standard tools to query schedule lists, fetch drug interactions, and write logs.
- **Shared Context State**: Nodes read/write session variables via `ctx.state` (such as the `needs_approval` flag and the compiled `draft_report`).
- **Human-in-the-Loop**: Uses `RequestInput` in `human_approval_gate` to pause execution, query the user, and resume with the input response.

---

## 4. Security Design

- **PII Scrubbing**: Regex filters automatically scrub SSNs, phone numbers, and email addresses from input, replacing them with generic redacted tokens.
- **Prompt Injection Detection**: Scans inputs for malicious override prompts (e.g. `"ignore previous instructions"`) and redirects them to the `security_alert` node immediately.
- **Structured Audit Logging**: Outputs JSON security logs (severity `INFO` or `CRITICAL` depending on threat assessment) to standard output for logging.
- **Domain-Specific Warning**: Medication manager warns the senior whenever they try to query a medication not present in the local database, requesting physician consultation.

---

## 5. MCP Server Design

The FastMCP server (`mcp_server.py`) provides 5 core tools:
1. `get_medication_info`: Accesses a database of side effects, typical dosages, and known interactions.
2. `get_daily_schedule`: Reads daily calendar details for medication slots and exercise intervals.
3. `update_schedule_item`: Marks list items as 'taken' or 'completed'.
4. `log_wellness_metric`: Logs health indicators (mood, pain scale, sleep) to a persistent metrics database.
5. `send_family_notification`: Transmits approved notifications to caregiver email/SMS.

---

## 6. Human-in-the-Loop (HITL) Flow

To prevent unauthorized sharing of health information, caregivers can only receive reports after explicit user approval:
1. When a report is requested, `wellness_reporter` compiles the logs and triggers the `request_report_approval` tool.
2. The workflow detects this and redirects the flow to `human_approval_gate`.
3. Execution **pauses** and a `RequestInput` is returned displaying the draft.
4. The user can review the draft report.
5. If approved, the report is dispatched via MCP and a success confirmation is returned.

---

## 7. Demo Walkthrough

1. **Daily Checklist Check**: The user asks for their daily medication and exercise checklist. The orchestrator delegates to `medication_manager` which uses the MCP schedule list to show pending duties.
2. **Weekly Summary Draft**: The user asks to draft their weekly log. `wellness_reporter` fetches logs and prompts the user with the draft for final review.
3. **Approval and Transmission**: The user replies `"yes"` to send the report. The gate executes `send_family_notification` and confirms.
4. **Safety Check**: The user attempts to input an override prompt. The checkpoint catches it and blocks the request instantly.

---

## 8. Impact / Value Statement
CareCompanion provides peace of mind for families, reduces medication adherence errors, and provides seniors with a respectful, patient, and helpful companion that adapts to their daily wellness needs.
