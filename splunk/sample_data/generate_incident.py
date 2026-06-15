#!/usr/bin/env python3
"""
ARIA Demo Incident Data Generator.

Generates a realistic DB connection pool exhaustion incident scenario:
  - db-primary connection pool fills from 45% → 100%
  - api-gateway response time spikes 50ms → 623ms
  - error rate climbs 0.1% → 14.7%
  - checkout-service errors cascade

Usage:
  python generate_incident.py              # print to stdout
  python generate_incident.py --send       # POST to running ARIA backend
  python generate_incident.py --splunk     # send to Splunk HEC endpoint
"""
import json
import random
import datetime
import argparse
import sys

# ── Scenario: DB connection pool exhaustion ────────────────────────────────


def generate_incident_timeline(
    start_time: datetime.datetime = None,
    duration_minutes: int = 15,
) -> list:
    """
    Generate a realistic incident timeline with correlated metrics.
    Returns list of log events in chronological order.
    """
    if start_time is None:
        start_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=duration_minutes)

    events = []
    services = {
        "db-primary": {
            "connection_pool_used": 45,
            "connection_pool_max": 100,
            "query_latency": 12,
        },
        "api-gateway": {
            "response_time": 50,
            "error_rate": 0.1,
            "cpu_percent": 22,
            "request_count": 1000,
        },
        "payment-service": {
            "response_time": 120,
            "error_rate": 0.0,
            "request_count": 200,
        },
        "checkout-service": {
            "response_time": 200,
            "error_rate": 0.0,
            "request_count": 150,
        },
        "user-service": {
            "response_time": 45,
            "error_rate": 0.0,
        },
    }

    # Incident progression: connection pool fills over 5 minutes
    # then cascades to all downstream services
    for minute in range(duration_minutes):
        t = start_time + datetime.timedelta(minutes=minute)
        progress = max(0, (minute - 2) / 5)  # starts escalating at minute 2

        # DB degrades
        pool_used = min(100, 45 + progress * 60 + random.gauss(0, 2))
        query_lat = 12 + progress * 200 + random.gauss(0, 5)

        # API degrades due to DB
        api_rt = 50 + progress * 600 + random.gauss(0, 20)
        api_err = 0.1 + progress * 15 + random.gauss(0, 0.5)

        # Downstream cascades (with lag)
        downstream_progress = max(0, (minute - 4) / 5)
        pay_rt = 120 + downstream_progress * 1100 + random.gauss(0, 30)
        pay_err = 0.0 + downstream_progress * 12 + random.gauss(0, 0.3)
        chk_rt = 200 + downstream_progress * 1300 + random.gauss(0, 40)
        chk_err = 0.0 + downstream_progress * 9 + random.gauss(0, 0.2)

        ts = t.isoformat() + "Z"

        events.extend([
            {
                "_time": ts, "sourcetype": "db_metrics",
                "host": "db-primary", "service": "db-primary",
                "connection_pool_used": round(max(0, pool_used), 1),
                "connection_pool_max": 100,
                "query_latency": round(max(1, query_lat), 1),
                "pool_utilization": round(min(100, pool_used), 1),
            },
            {
                "_time": ts, "sourcetype": "app_metrics",
                "host": "api-gateway", "service": "api-gateway",
                "response_time": round(max(10, api_rt), 1),
                "error_rate": round(max(0, api_err), 2),
                "cpu_percent": round(22 + progress * 40, 1),
                "request_count": int(1000 + random.gauss(0, 50)),
                "level": "ERROR" if api_err > 2 else "INFO",
            },
            {
                "_time": ts, "sourcetype": "app_metrics",
                "host": "payment-service", "service": "payment-service",
                "response_time": round(max(10, pay_rt), 1),
                "error_rate": round(max(0, pay_err), 2),
                "request_count": int(200 + random.gauss(0, 10)),
                "level": "ERROR" if pay_err > 2 else "INFO",
            },
            {
                "_time": ts, "sourcetype": "app_metrics",
                "host": "checkout-service", "service": "checkout-service",
                "response_time": round(max(10, chk_rt), 1),
                "error_rate": round(max(0, chk_err), 2),
                "request_count": int(150 + random.gauss(0, 8)),
                "level": "ERROR" if chk_err > 1 else "INFO",
            },
        ])

    return events


def generate_trigger_event(events: list) -> dict:
    """Generate the Splunk alert trigger event that kicks off ARIA."""
    # Find peak checkout error rate
    checkout_events = [e for e in events if e["service"] == "checkout-service"]
    peak = max(checkout_events, key=lambda e: e["error_rate"])
    return {
        "alert_name": "high_error_rate_checkout",
        "service": "checkout-service",
        "metric": "error_rate",
        "value": peak["error_rate"],
        "threshold": 5.0,
        "timestamp": peak["_time"],
        "severity": "P2",
    }


def main():
    parser = argparse.ArgumentParser(description="ARIA Demo Incident Generator")
    parser.add_argument("--send", action="store_true", help="POST to ARIA backend")
    parser.add_argument("--splunk", action="store_true", help="Send to Splunk HEC")
    parser.add_argument("--url", default="http://localhost:8000", help="ARIA backend URL")
    parser.add_argument("--splunk-url", default="http://localhost:8088", help="Splunk HEC URL")
    parser.add_argument("--splunk-token", default="", help="Splunk HEC token")
    parser.add_argument("--minutes", type=int, default=15, help="Incident duration in minutes")
    parser.add_argument("--output", help="Write events to JSON file")
    args = parser.parse_args()

    print("Generating ARIA demo incident: DB connection pool exhaustion...")
    events = generate_incident_timeline(duration_minutes=args.minutes)
    trigger = generate_trigger_event(events)

    print(f"Generated {len(events)} log events over {args.minutes} minutes")
    print(f"Peak error rate: {trigger['value']:.1f}% on {trigger['service']}")

    payload = {"events": events, "trigger": trigger}

    if args.output:
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Written to {args.output}")
    elif args.send:
        import urllib.request
        body = json.dumps({
            "severity": "P2",
            "trigger_event": trigger,
        }).encode()
        req = urllib.request.Request(
            f"{args.url}/api/incidents",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        print(f"Incident created: {result['id']}")
        print(f"Connect to: ws://localhost:8000/ws/incident/{result['id']}")
    elif args.splunk:
        # Send events to Splunk HEC
        import urllib.request
        hec_events = [{"time": e["_time"], "event": e, "sourcetype": e["sourcetype"]} for e in events]
        for ev in hec_events:
            body = json.dumps(ev).encode()
            req = urllib.request.Request(
                f"{args.splunk_url}/services/collector/event",
                data=body,
                headers={
                    "Authorization": f"Splunk {args.splunk_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                urllib.request.urlopen(req)
            except Exception as e:
                print(f"HEC send failed: {e}", file=sys.stderr)
        print(f"Sent {len(hec_events)} events to Splunk HEC at {args.splunk_url}")
    else:
        # Print summary to stdout
        print("\nSample events (first 3):")
        for ev in events[:3]:
            print(json.dumps(ev, indent=2))
        print(f"\nTrigger event:\n{json.dumps(trigger, indent=2)}")
        print("\nRun with --send to POST to ARIA backend")
        print("Run with --output events.json to save all events")


if __name__ == "__main__":
    main()
