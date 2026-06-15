"""
ARIA Alert Action — "AI for Splunk Apps" integration.

This Python script runs inside Splunk Enterprise using the Splunk Python SDK.
When any configured alert fires, Splunk executes this script, which calls
the ARIA REST API to start the agentic incident investigation pipeline.

This is what "AI for Splunk Apps — Build agentic workflows inside Splunk apps
using the Python SDK" means in the hackathon context.

How it fits in the architecture:
  Splunk alert fires
    → Splunk executes this script (Python SDK / modular alert action)
      → POST to ARIA backend /api/incidents
        → ARIA orchestrator starts 4-agent LangGraph pipeline
          → Sentinel, Forensic, Propagation, Remediation agents run
            → Results streamed to War Room dashboard via WebSocket

Install: place this file in splunk/app/bin/aria_trigger.py
         then install the splunk/app/ folder as a Splunk app.
"""
import sys
import json
import urllib.request
import urllib.error
import os

# Splunk modular alert actions receive the alert payload via stdin as JSON
def main():
    payload = json.loads(sys.stdin.read())

    # Extract alert context from Splunk payload
    result    = payload.get("result", {})
    search_name = payload.get("search_name", "unknown_alert")
    app_name  = payload.get("app", "search")

    # Map Splunk alert severity to ARIA severity
    # Splunk severity: 1=debug, 2=info, 3=warn, 4=error, 5=severe, 6=fatal
    splunk_sev = int(payload.get("severity", "3"))
    aria_sev   = {6: "P1", 5: "P1", 4: "P2", 3: "P3"}.get(splunk_sev, "P4")

    # Build the ARIA incident trigger payload
    aria_payload = {
        "severity": aria_sev,
        "trigger_event": {
            "alert_name":  search_name,
            "service":     result.get("service", result.get("host", "unknown")),
            "metric":      result.get("metric", "error_rate"),
            "value":       float(result.get("error_rate", result.get("count", 0))),
            "threshold":   5.0,
            "raw_data":    result,
        },
    }

    # ARIA backend URL — configurable via environment or hardcoded default
    aria_url = os.environ.get("ARIA_API_URL", "http://localhost:8000")
    endpoint = f"{aria_url}/api/incidents"

    try:
        body = json.dumps(aria_payload).encode("utf-8")
        req  = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = json.loads(resp.read().decode())
            incident_id   = response_data.get("id", "unknown")
            print(
                f"ARIA incident created: {incident_id} "
                f"(severity={aria_sev}, alert={search_name})",
                file=sys.stderr,
            )
    except urllib.error.URLError as e:
        print(f"ARIA trigger failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
