"""
ARIA Configuration — reads from environment variables / .env file.

Priority:
  1. Real environment variables (Docker, CI, production)
  2. .env file in the project root
  3. Hardcoded defaults below (safe for local dev)
"""
import os
from dotenv import load_dotenv

load_dotenv()   # no-op if .env doesn't exist


class Settings:
    # ── Splunk connection ──────────────────────────────────────────────────
    SPLUNK_HOST: str = os.getenv("SPLUNK_HOST", "localhost")
    SPLUNK_PORT: int = int(os.getenv("SPLUNK_PORT", "8089"))
    SPLUNK_TOKEN: str = os.getenv("SPLUNK_TOKEN", "")

    # MCP Server URL — the endpoint installed by the Splunk MCP Server app.
    # Default matches the standard path after installing app 7931.
    SPLUNK_MCP_URL: str = os.getenv(
        "SPLUNK_MCP_URL",
        f"https://{os.getenv('SPLUNK_HOST', 'localhost')}:{os.getenv('SPLUNK_PORT', '8089')}/services/mcp/v1",
    )

    # ── Demo mode ──────────────────────────────────────────────────────────
    # When True, all Splunk MCP calls return realistic synthetic data.
    # The causal AI, LangGraph orchestration, WebSocket streaming, and
    # all frontend visualisations work fully without a Splunk instance.
    # Set to False once you have Splunk + MCP Server app configured.
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

    # ── Redis ──────────────────────────────────────────────────────────────
    # Optional — incident state is held in memory when Redis is unavailable.
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # ── LLM fallback ──────────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

    # ── App ────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    # Auto-approve Low-risk runbook steps after this many seconds
    AUTO_APPROVE_LOW_RISK: bool = True
    AUTO_APPROVE_TIMEOUT_SECONDS: int = int(
        os.getenv("AUTO_APPROVE_TIMEOUT_SECONDS", "30")
    )

    def __repr__(self) -> str:
        token_preview = f"{self.SPLUNK_TOKEN[:6]}…" if self.SPLUNK_TOKEN else "(not set)"
        return (
            f"Settings(host={self.SPLUNK_HOST}:{self.SPLUNK_PORT}, "
            f"demo={self.DEMO_MODE}, token={token_preview})"
        )


settings = Settings()
