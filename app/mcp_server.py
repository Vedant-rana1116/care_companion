from mcp.server.fastmcp import FastMCP
import json
import os
from datetime import datetime

# Initialize FastMCP server
mcp = FastMCP("CareCompanion MCP Server")

# In-memory medication database for demo purposes
MEDICATION_DATABASE = {
    "aspirin": {
        "dosage": "81mg once daily",
        "timing": "Morning with food",
        "warnings": "Avoid taking with other NSAIDs (e.g. ibuprofen). Watch for bleeding.",
        "interactions": ["ibuprofen", "warfarin", "clopidogrel"]
    },
    "lisinopril": {
        "dosage": "10mg once daily",
        "timing": "Morning, consistent time",
        "warnings": "May cause dizziness or a dry cough. Monitor blood pressure.",
        "interactions": ["spironolactone", "potassium supplements"]
    },
    "metformin": {
        "dosage": "500mg twice daily",
        "timing": "With breakfast and dinner",
        "warnings": "Take with meals to decrease stomach upset. Watch for signs of low blood sugar.",
        "interactions": ["contrast dye", "cimetidine"]
    },
    "atorvastatin": {
        "dosage": "20mg once daily",
        "timing": "Evening",
        "warnings": "Avoid excessive grapefruit juice. Report unusual muscle pain.",
        "interactions": ["grapefruit juice", "clarithromycin"]
    }
}

# Simulated files for local database
SCHEDULE_FILE = "daily_schedule.json"
METRICS_FILE = "wellness_metrics.json"

def _load_json(file_path: str, default_data: dict) -> dict:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            return default_data
    return default_data

def _save_json(file_path: str, data: dict):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# Set up default daily schedule if file doesn't exist
DEFAULT_SCHEDULE = {
    "medications": [
        {"time": "08:00 AM", "name": "lisinopril", "status": "pending"},
        {"time": "08:00 AM", "name": "metformin", "status": "pending"},
        {"time": "08:00 PM", "name": "metformin", "status": "pending"},
        {"time": "08:00 PM", "name": "atorvastatin", "status": "pending"}
    ],
    "exercises": [
        {"time": "10:30 AM", "activity": "15-minute gentle chair stretching", "status": "pending"},
        {"time": "04:00 PM", "activity": "10-minute backyard walk", "status": "pending"}
    ]
}

@mcp.tool()
def get_medication_info(medication_name: str) -> str:
    """Retrieves safety, dosage, timing, and interaction info for a medication.
    
    Args:
        medication_name: The name of the medication to look up (e.g. aspirin, metformin).
    """
    name_lower = medication_name.lower().strip()
    if name_lower in MEDICATION_DATABASE:
        info = MEDICATION_DATABASE[name_lower]
        return json.dumps({
            "medication": medication_name,
            "dosage": info["dosage"],
            "timing": info["timing"],
            "warnings": info["warnings"],
            "known_interactions": info["interactions"]
        }, indent=2)
    else:
        return f"Medication '{medication_name}' was not found in the local pharmacy database. Please consult a doctor or pharmacist for official details."

@mcp.tool()
def get_daily_schedule() -> str:
    """Retrieves the current daily medication and exercise schedule."""
    schedule = _load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
    return json.dumps(schedule, indent=2)

@mcp.tool()
def update_schedule_item(item_type: str, item_name: str, status: str) -> str:
    """Updates the status of a schedule item (e.g. marking a medication as 'taken' or exercise as 'completed').
    
    Args:
        item_type: Either 'medications' or 'exercises'.
        item_name: The name of the medication or the activity description.
        status: The new status (e.g., 'taken', 'completed', 'pending').
    """
    schedule = _load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
    updated = False
    
    if item_type in schedule:
        for item in schedule[item_type]:
            # Match medication name or exercise description
            name_key = "name" if item_type == "medications" else "activity"
            if item.get(name_key, "").lower() == item_name.lower():
                item["status"] = status
                updated = True
                
    if updated:
        _save_json(SCHEDULE_FILE, schedule)
        return f"Successfully updated status of {item_type[:-1]} '{item_name}' to '{status}'."
    return f"Could not find {item_type[:-1]} '{item_name}' in the schedule."

@mcp.tool()
def log_wellness_metric(metric_type: str, value: str) -> str:
    """Logs a senior wellness metric (e.g. pain level, blood pressure, sleep quality, mood).
    
    Args:
        metric_type: The type of metric (e.g., 'pain_level', 'blood_pressure', 'sleep', 'mood').
        value: The value to log (e.g., '3/10', '120/80', '7 hours', 'happy').
    """
    metrics = _load_json(METRICS_FILE, {"logs": []})
    new_log = {
        "timestamp": datetime.now().isoformat(),
        "metric": metric_type,
        "value": value
    }
    metrics["logs"].append(new_log)
    _save_json(METRICS_FILE, metrics)
    return f"Logged wellness metric: {metric_type} = {value} at {new_log['timestamp']}"

@mcp.tool()
def send_family_notification(report_content: str) -> str:
    """Simulates sending the approved wellness report to family members/caregivers.
    
    Args:
        report_content: The full body of the wellness report to send.
    """
    notification_log = "family_notifications.txt"
    timestamp = datetime.now().isoformat()
    log_entry = f"--- SENT NOTIFICATION at {timestamp} ---\n{report_content}\n---------------------------------------\n\n"
    with open(notification_log, "a") as f:
        f.write(log_entry)
    return "SUCCESS: Wellness report has been transmitted to your family contact list."

if __name__ == "__main__":
    mcp.run(transport="stdio")
