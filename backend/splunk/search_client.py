"""
Direct Splunk REST API search client.
Used as fallback when MCP server is unavailable,
and for non-MCP operations like index management.
"""
import httpx
import asyncio
import json
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


class SplunkSearchClient:
    """
    Direct Splunk REST API client.
    Implements search job creation + polling pattern.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
    ):
        self.host = host or settings.SPLUNK_HOST
        self.port = port or settings.SPLUNK_PORT
        self.token = token or settings.SPLUNK_TOKEN
        self.base_url = f"https://{self.host}:{self.port}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                verify=False,  # Splunk often uses self-signed certs
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=60.0,
            )
        return self._client

    async def search(
        self,
        spl: str,
        earliest_time: str = "-1h",
        latest_time: str = "now",
        max_results: int = 10000,
    ) -> list:
        """
        Execute a Splunk search and return results.
        Uses the async search job API (create → poll → fetch).
        """
        client = await self._get_client()

        # 1. Create search job
        create_resp = await client.post(
            f"{self.base_url}/services/search/jobs",
            data={
                "search": f"search {spl}",
                "earliest_time": earliest_time,
                "latest_time": latest_time,
                "output_mode": "json",
            },
        )
        create_resp.raise_for_status()
        sid = create_resp.json()["sid"]

        # 2. Poll until done
        for _ in range(60):  # max 60s
            status_resp = await client.get(
                f"{self.base_url}/services/search/jobs/{sid}",
                params={"output_mode": "json"},
            )
            status_resp.raise_for_status()
            state = status_resp.json()["entry"][0]["content"]["dispatchState"]
            if state == "DONE":
                break
            elif state in ("FAILED", "FATAL"):
                raise RuntimeError(f"Splunk search failed: {state}")
            await asyncio.sleep(1)

        # 3. Fetch results
        results_resp = await client.get(
            f"{self.base_url}/services/search/jobs/{sid}/results",
            params={"output_mode": "json", "count": max_results},
        )
        results_resp.raise_for_status()
        return results_resp.json().get("results", [])

    async def get_saved_searches(self) -> list:
        client = await self._get_client()
        resp = await client.get(
            f"{self.base_url}/services/saved/searches",
            params={"output_mode": "json"},
        )
        resp.raise_for_status()
        return resp.json().get("entry", [])

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
