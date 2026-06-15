"""
Splunk Hosted Model calls via MCP.
Wraps Splunk MLTK / AI-for-IT models.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SplunkHostedModels:
    """
    Interface for Splunk hosted ML models.
    All calls route through the MCP client.
    """

    def __init__(self, mcp_client):
        self.mcp = mcp_client

    async def run_anomaly_detection(
        self,
        metrics_data: dict,
        model_name: str = "foundation-sec-1.1-8b-instruct"
    ) -> dict:
        """
        Run Splunk Foundation AI Security Model for anomaly classification.
        Falls back to local Z-score detection when Splunk is unavailable.
        """
        try:
            result = await self.mcp.run_hosted_model(
                model=model_name,
                input_data={
                    "data": metrics_data,
                    "algorithm": "IsolationForest",
                    "contamination": 0.1,
                }
            )
            return result
        except Exception as e:
            logger.warning(f"Hosted model unavailable ({e}), using local fallback")
            return self._local_anomaly_fallback(metrics_data)

    async def run_forecast(
        self,
        timeseries: list,
        horizon_minutes: int = 5,
        model_name: str = "cisco-deep-time-series"
    ) -> dict:
        """
        Run Cisco Deep Time Series Model for metric forecasting.
        Used by Propagation Agent to estimate blast radius ETAs.
        Falls back to linear extrapolation when Splunk is unavailable.
        """
        try:
            result = await self.mcp.run_hosted_model(
                model=model_name,
                input_data={
                    "timeseries": timeseries,
                    "horizon": horizon_minutes,
                    "algorithm": "StateSpaceModel",
                }
            )
            return result
        except Exception as e:
            logger.warning(f"Forecast model unavailable ({e}), using linear extrapolation")
            return self._linear_forecast_fallback(timeseries, horizon_minutes)

    async def run_nlp_summary(
        self,
        incident_data: dict,
        model_name: str = "foundation-sec-1.1-8b-instruct"
    ) -> str:
        """
        Use Foundation AI Security Model to generate incident summary narrative.
        Falls back to template when Splunk is unavailable.
        """
        try:
            result = await self.mcp.run_hosted_model(
                model=model_name,
                input_data=incident_data
            )
            return result.get("summary", "")
        except Exception as e:
            logger.warning(f"NLP model unavailable ({e}), using template")
            return self._template_summary(incident_data)


    def _local_anomaly_fallback(self, metrics_data: dict) -> dict:
        """
        Simple Z-score anomaly detection as fallback.
        """
        import numpy as np
        anomalies = {}
        for metric, values in metrics_data.items():
            arr = np.array(values, dtype=float)
            if len(arr) < 3:
                continue
            z = (arr - arr.mean()) / (arr.std() + 1e-9)
            anomalies[metric] = {
                "is_anomaly": bool(np.any(np.abs(z) > 2.5)),
                "anomaly_score": float(np.max(np.abs(z))),
                "anomaly_indices": [int(i) for i in np.where(np.abs(z) > 2.5)[0]],
            }
        return anomalies

    def _linear_forecast_fallback(
        self,
        timeseries: list,
        horizon_minutes: int
    ) -> dict:
        """
        Linear regression extrapolation as forecast fallback.
        """
        import numpy as np
        values = [p["value"] for p in timeseries]
        x = np.arange(len(values))
        if len(x) < 2:
            return {"forecast": [{"minute": i, "value": values[-1]} for i in range(horizon_minutes)]}
        coeffs = np.polyfit(x, values, 1)
        slope, intercept = coeffs
        n = len(values)
        forecast = [
            {"minute": i + 1, "value": float(slope * (n + i) + intercept)}
            for i in range(horizon_minutes)
        ]
        return {"forecast": forecast, "trend": "increasing" if slope > 0 else "decreasing"}

    def _template_summary(self, data: dict) -> str:
        svc = data.get("service", "unknown")
        rc = data.get("root_cause", "unknown")
        conf = data.get("confidence", 0.0)
        return (
            f"Incident detected on {svc}. "
            f"Root cause identified as {rc} with {conf:.0%} confidence. "
            f"Automated remediation initiated pending approval."
        )
