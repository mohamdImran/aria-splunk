"""
Reusable SPL query templates for ARIA agents.
All queries are parameterized to avoid injection.
"""
from typing import Optional


class SPLTemplates:
    """Collection of parameterized SPL query templates."""

    @staticmethod
    def anomaly_detection(service: str, time_range: str = "-30m") -> str:
        return f"""
index=main service="{service}" earliest={time_range}
| timechart span=1m avg(response_time) as rt, avg(error_rate) as err, sum(request_count) as reqs
| apply anomaly_detection_model
| where IsAnomaly=1
""".strip()

    @staticmethod
    def service_metrics(service: str, time_range: str = "-1h") -> str:
        return f"""
index=main service="{service}" earliest={time_range}
| timechart span=1m
    avg(response_time) as response_time_ms,
    avg(error_rate) as error_rate_pct,
    avg(cpu_percent) as cpu_percent,
    avg(memory_percent) as memory_percent,
    sum(request_count) as request_count
""".strip()

    @staticmethod
    def error_spike(service: str, time_range: str = "-15m") -> str:
        return f"""
index=main service="{service}" level=ERROR earliest={time_range}
| timechart span=1m count as error_count
| streamstats window=5 avg(error_count) as baseline
| eval spike = if(error_count > baseline * 3, 1, 0)
| where spike=1
""".strip()

    @staticmethod
    def service_topology(time_range: str = "-24h") -> str:
        return f"""
index=main earliest={time_range}
| stats count by host, sourcetype
| join type=outer host [search index=service_deps | table host, depends_on]
| stats dc(depends_on) as dep_count by host
""".strip()

    @staticmethod
    def db_connection_pool(db_host: str, time_range: str = "-30m") -> str:
        return f"""
index=main host="{db_host}" sourcetype="db_metrics" earliest={time_range}
| timechart span=1m
    avg(connection_pool_used) as pool_used,
    avg(connection_pool_max) as pool_max,
    avg(query_latency_ms) as query_latency
| eval pool_utilization = round(pool_used / pool_max * 100, 2)
""".strip()

    @staticmethod
    def multi_service_corr(services: list, metric: str, time_range: str = "-1h") -> str:
        svc_filter = " OR ".join([f'service="{s}"' for s in services])
        return f"""
index=main ({svc_filter}) earliest={time_range}
| timechart span=1m avg({metric}) by service
""".strip()

    @staticmethod
    def active_alerts(time_range: str = "-1h") -> str:
        return f"""
index=_internal source=*scheduler* status=fired earliest={time_range}
| stats latest(_time) as last_fired, count as fire_count by savedsearch_name, app
| sort - fire_count
""".strip()

    @staticmethod
    def causal_metric_window(
        services: list,
        metrics: list,
        time_range: str = "-1h",
        span: str = "1m"
    ) -> str:
        svc_filter = " OR ".join([f'service="{s}"' for s in services])
        metric_aggs = " ".join([f"avg({m}) as {m}" for m in metrics])
        return f"""
index=main ({svc_filter}) earliest={time_range}
| timechart span={span} {metric_aggs} by service
""".strip()

    @staticmethod
    def runbook_action_restart(service: str) -> str:
        return f"""
| rest /services/apps/local/{service}/restart method=POST
""".strip()

    @staticmethod
    def create_alert(
        name: str,
        search: str,
        cron: str = "*/5 * * * *",
        threshold: float = 0.0
    ) -> dict:
        """Returns kwargs dict for alert creation via MCP."""
        return {
            "name": name,
            "search": search,
            "cron_schedule": cron,
            "alert_threshold": threshold,
            "actions": "email,webhook",
        }
