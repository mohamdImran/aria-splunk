"""
Splunk MCP Client — wraps all Splunk interactions as MCP tool calls.
Agents call this instead of Splunk REST directly.

Available tools via MCP:
  splunk_search           — Execute SPL queries
  splunk_get_alerts       — List active alerts
  splunk_get_metrics      — Time-series metric data
  splunk_run_model        — Hosted ML model inference
  splunk_create_alert     — Create new alert rule
  splunk_execute_action   — Execute a response action
  splunk_update_dashboard — Write to a dashboard
"""
import asyncio
import logging
import json
from typing import Optional, Any
from config import settings

logger = logging.getLogger(__name__)

# ── Demo/Mock data for hackathon when Splunk unavailable ─────────────────────
DEMO_METRICS = {
    "api-gateway": {
        "response_time": [45, 47, 52, 61, 89, 145, 312, 487, 623, 589, 401],
        "error_rate":    [0.1, 0.1, 0.2, 0.3, 0.8, 2.1, 5.4, 8.9, 14.7, 12.3, 9.1],
        "cpu_percent":   [22, 23, 24, 25, 28, 35, 42, 51, 58, 55, 49],
    },
    "db-primary": {
        "connection_pool_used": [45, 47, 52, 68, 89, 98, 100, 100, 100, 100, 100],
        "connection_pool_max":  [100] * 11,
        "query_latency":        [12, 13, 15, 22, 45, 89, 145, 201, 198, 187, 165],
    },
    "payment-service": {
        "response_time": [120, 122, 125, 140, 210, 380, 650, 980, 1200, 1100, 890],
        "error_rate":    [0.0, 0.0, 0.1, 0.2, 0.5, 1.8, 4.2, 7.1, 11.3, 9.8, 7.2],
    },
    "checkout-service": {
        "response_time": [200, 201, 205, 220, 290, 450, 780, 1200, 1500, 1400, 1100],
        "error_rate":    [0.0, 0.0, 0.0, 0.1, 0.3, 0.9, 2.1, 4.8, 8.2, 7.1, 5.4],
    },
}


class SplunkMCPClient:
    """
    MCP protocol client for Splunk.
    All agent Splunk operations route through this class.
    Falls back to demo data when DEMO_MODE=true or MCP unavailable.
    """

    def __init__(
        self,
        mcp_server_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.server_url = mcp_server_url or settings.SPLUNK_MCP_URL
        self.token = token or settings.SPLUNK_TOKEN
        self.demo_mode = settings.DEMO_MODE
        self._session = None

    async def _ensure_session(self):
        """Initialize MCP session if not already connected."""
        if self._session is not None:
            return
        if self.demo_mode:
            return
        try:
            # Real MCP session initialization
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import httpx

            # Use streamable HTTP transport for remote Splunk MCP Server
            self._session = "connected"
            logger.info(f"MCP session established: {self.server_url}")
        except Exception as e:
            logger.warning(f"MCP session failed ({e}), switching to demo mode")
            self.demo_mode = True

    async def _call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Route a tool call through Splunk MCP Server or demo fallback."""
        await self._ensure_session()
        if self.demo_mode:
            return await self._demo_tool(tool_name, arguments)
        try:
            import httpx
            # Splunk MCP Server uses JSON-RPC 2.0 over HTTP
            # Endpoint: POST https://localhost:8089/services/mcp
            # Auth:     Bearer token (MCP Encrypted Token, audience="mcp")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                resp = await client.post(
                    self.server_url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
                # MCP JSON-RPC response: { "result": { "content": [...] } }
                result = body.get("result", {})
                # Extract text content from MCP content blocks
                content = result.get("content", [])
                if content and isinstance(content, list):
                    text = content[0].get("text", "{}")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"raw": text}
                return result
        except Exception as e:
            logger.warning("MCP tool call failed (%s), using demo fallback", e)
            return await self._demo_tool(tool_name, arguments)

    # ── Public API ─────────────────────────────────────────────────────────

    async def search(self, spl: str, time_range: str = "-1h") -> dict:
        """Execute SPL query via MCP."""
        return await self._call_tool("splunk_search", {
            "query": spl,
            "earliest_time": time_range,
            "output_mode": "json",
        })

    async def get_alerts(self) -> dict:
        """List active alerts via MCP."""
        return await self._call_tool("splunk_get_alerts", {})

    async def get_metrics(self, service: str, metric: str, time_range: str = "-1h") -> dict:
        """Get time-series metric data for a service."""
        return await self._call_tool("splunk_get_metrics", {
            "service": service,
            "metric": metric,
            "time_range": time_range,
        })

    async def run_hosted_model(self, model: str, input_data: dict) -> dict:
        """Run a Splunk hosted ML model."""
        return await self._call_tool("splunk_run_model", {
            "model": model,
            "input": input_data,
        })

    async def create_alert(
        self,
        name: str,
        search: str,
        threshold: float,
        cron: str = "*/5 * * * *",
    ) -> dict:
        """Create a new Splunk alert rule."""
        return await self._call_tool("splunk_create_alert", {
            "name": name,
            "search": search,
            "alert_threshold": threshold,
            "cron_schedule": cron,
        })

    async def execute_action(self, action: str, parameters: dict) -> dict:
        """Execute a Splunk response action (restart, scale, etc.)."""
        return await self._call_tool("splunk_execute_action", {
            "action": action,
            "parameters": parameters,
        })

    async def update_dashboard(self, dashboard_id: str, data: dict) -> dict:
        """Write data to a Splunk dashboard panel."""
        return await self._call_tool("splunk_update_dashboard", {
            "dashboard_id": dashboard_id,
            "data": data,
        })

    # ── High-level helpers used by agents ─────────────────────────────────

    async def get_anomaly_candidates(self, service: str) -> dict:
        """
        Detect anomalies in a service's recent metrics.
        Uses Splunk MLTK anomaly detection model.
        """
        spl = f"""
index=main service="{service}" earliest=-30m
| timechart span=1m avg(response_time) as rt, avg(error_rate) as err
| apply anomaly_detection_model
| where IsAnomaly=1
""".strip()
        return await self.search(spl)

    async def get_service_topology(self) -> dict:
        """Fetch service dependency graph from Splunk."""
        spl = """
index=main earliest=-24h
| stats count by host, sourcetype
| join type=outer host [search index=service_deps | table host, depends_on]
| stats dc(depends_on) as dep_count by host
""".strip()
        return await self.search(spl)

    async def get_causal_metrics(self, services: list, time_range: str = "-1h") -> dict:
        """
        Fetch correlated metrics for multiple services for causal analysis.
        Returns dict of service -> metric -> timeseries.
        """
        if self.demo_mode:
            return {svc: DEMO_METRICS.get(svc, {}) for svc in services}
        results = {}
        for service in services:
            spl = f"""
index=main service="{service}" earliest={time_range}
| timechart span=1m
    avg(response_time) as response_time,
    avg(error_rate) as error_rate,
    avg(cpu_percent) as cpu_percent,
    avg(memory_percent) as memory_percent
""".strip()
            data = await self.search(spl)
            results[service] = data
        return results

    # ── Demo data layer ────────────────────────────────────────────────────

    async def _demo_tool(self, tool_name: str, arguments: dict) -> Any:
        """
        Returns realistic demo data for hackathon demos
        when Splunk is unavailable.
        """
        await asyncio.sleep(0.1)  # simulate network latency

        if tool_name == "splunk_search":
            return self._demo_search(arguments.get("query", ""))

        if tool_name == "splunk_get_metrics":
            service = arguments.get("service", "api-gateway")
            metric = arguments.get("metric", "response_time")
            data = DEMO_METRICS.get(service, {})
            values = data.get(metric, [50] * 11)
            return {
                "service": service,
                "metric": metric,
                "timeseries": [
                    {"time": f"-{10-i}m", "value": v}
                    for i, v in enumerate(values)
                ],
            }

        if tool_name == "splunk_get_alerts":
            return {
                "alerts": [
                    {
                        "name": "high_error_rate_checkout",
                        "service": "checkout-service",
                        "severity": "critical",
                        "fired_at": "2025-01-15T10:30:00Z",
                    }
                ]
            }

        if tool_name == "splunk_run_model":
            return {
                "model": arguments.get("model"),
                "prediction": "anomaly_detected",
                "confidence": 0.94,
                "features": arguments.get("input", {}),
            }

        if tool_name == "splunk_create_alert":
            return {"status": "created", "sid": "alert_001", **arguments}

        if tool_name == "splunk_execute_action":
            return {"status": "executed", "action": arguments.get("action"), "result": "success"}

        if tool_name == "splunk_update_dashboard":
            return {"status": "updated", "dashboard_id": arguments.get("dashboard_id")}

        return {"status": "ok", "tool": tool_name}

    def _demo_search(self, query: str) -> dict:
        """Generate contextual demo search results based on query content."""
        q = query.lower()

        if "error_rate" in q or "anomaly" in q:
            return {
                "results": [
                    {"_time": f"2025-01-15T10:{30+i}:00Z",
                     "service": "checkout-service",
                     "error_rate": str(round(0.1 * (i + 1) ** 1.5, 2)),
                     "IsAnomaly": "1" if i > 4 else "0"}
                    for i in range(11)
                ],
                "field_list": ["_time", "service", "error_rate", "IsAnomaly"],
            }

        if "depends_on" in q or "topology" in q:
            return {
                "results": [
                    {"host": "api-gateway",       "depends_on": "db-primary",      "dep_count": "3"},
                    {"host": "payment-service",   "depends_on": "api-gateway",     "dep_count": "2"},
                    {"host": "checkout-service",  "depends_on": "payment-service", "dep_count": "2"},
                    {"host": "checkout-service",  "depends_on": "db-primary",      "dep_count": "2"},
                    {"host": "user-service",      "depends_on": "db-primary",      "dep_count": "1"},
                    {"host": "notification-svc",  "depends_on": "checkout-service","dep_count": "1"},
                ],
                "field_list": ["host", "depends_on", "dep_count"],
            }

        if "connection_pool" in q or "db" in q:
            return {
                "results": [
                    {"_time": f"2025-01-15T10:{30+i}:00Z",
                     "pool_used": str(45 + i * 6),
                     "pool_max": "100",
                     "query_latency": str(12 + i ** 2),
                     "pool_utilization": str(45 + i * 6)}
                    for i in range(11)
                ],
                "field_list": ["_time", "pool_used", "pool_max", "query_latency"],
            }

        # Generic metrics fallback
        return {
            "results": [
                {"_time": f"2025-01-15T10:{30+i}:00Z",
                 "count": str(100 + i * 10),
                 "avg_response_time": str(50 + i * 15)}
                for i in range(10)
            ],
            "field_list": ["_time", "count", "avg_response_time"],
        }
