"""
WebSocket router — real-time incident communication channel.

Each incident gets its own room keyed by incident_id.
The frontend connects as soon as it knows the ID, then immediately
sends { type: "get_state" } to receive a full state replay for
late-joining clients (e.g. when triggered via curl).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Thread-safe per-incident WebSocket room manager."""

    def __init__(self) -> None:
        self._rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, incident_id: str) -> None:
        await ws.accept()
        self._rooms.setdefault(incident_id, []).append(ws)
        logger.info("WS connected  incident=%s  total=%d",
                    incident_id, len(self._rooms[incident_id]))

    def disconnect(self, ws: WebSocket, incident_id: str) -> None:
        room = self._rooms.get(incident_id, [])
        if ws in room:
            room.remove(ws)
        logger.info("WS disconnected  incident=%s  remaining=%d",
                    incident_id, len(room))

    async def broadcast(self, incident_id: str, message: dict) -> None:
        """Deliver a message to every client watching this incident."""
        room = list(self._rooms.get(incident_id, []))
        dead: list[WebSocket] = []
        for ws in room:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug("WS send failed incident=%s: %s", incident_id, exc)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, incident_id)

    async def broadcast_all(self, message: dict) -> None:
        """Broadcast to every connected client across all incidents."""
        for iid in list(self._rooms):
            await self.broadcast(iid, message)

    def room_size(self, incident_id: str) -> int:
        return len(self._rooms.get(incident_id, []))


manager = ConnectionManager()


@router.websocket("/ws/incident/{incident_id}")
async def incident_ws(ws: WebSocket, incident_id: str) -> None:
    """
    Per-incident WebSocket endpoint.

    Client → server messages
    ─────────────────────────
    { type: "get_state" }
        Replay the latest persisted state — handles late-joiners.

    { type: "approval_response", approved: bool, notes?: string }
        Unblock the human-approval gate in the orchestrator.

    { type: "ping" }
        Keep-alive; server replies with { type: "pong" }.

    Server → client messages
    ─────────────────────────
    connected | state_snapshot | agent_status | agent_message |
    causal_update | blast_update | approval_required |
    auto_approve_countdown | incident_brief |
    incident_started | incident_completed | execution_update
    """
    await manager.connect(ws, incident_id)

    try:
        # Announce connection immediately so the client can request a replay
        await ws.send_json({
            "type":        "connected",
            "incident_id": incident_id,
            "message":     "ARIA War Room connected",
        })

        while True:
            data     = await ws.receive_json()
            msg_type = data.get("type")

            # ── State replay ───────────────────────────────────────────────
            if msg_type == "get_state":
                await _handle_get_state(ws, incident_id)

            # ── Human approval ─────────────────────────────────────────────
            elif msg_type == "approval_response":
                await _handle_approval(ws, incident_id, data)

            # ── Keep-alive ─────────────────────────────────────────────────
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            # ── Unknown ────────────────────────────────────────────────────
            else:
                logger.debug("Unknown WS message type=%s incident=%s",
                             msg_type, incident_id)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("WS error incident=%s: %s", incident_id, exc)
    finally:
        manager.disconnect(ws, incident_id)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _handle_get_state(ws: WebSocket, incident_id: str) -> None:
    """
    Send the persisted state back to a single client.

    Tries Redis first (full pipeline state), then falls back to the
    in-memory incident record (status + brief), so the frontend always
    gets *something* useful even when Redis is unavailable.
    """
    from main import get_incident_state  # deferred to avoid circular import

    state: Optional[dict] = await get_incident_state(incident_id)

    if state:
        await ws.send_json({"type": "state_snapshot", "state": state})
        logger.debug("Sent state_snapshot  incident=%s (from Redis)", incident_id)
        return

    # Redis unavailable — reconstruct a minimal snapshot from the incident record
    from routers.incidents import get_all_incidents
    incidents = get_all_incidents()
    incident  = incidents.get(incident_id)

    if incident is None:
        await ws.send_json({
            "type":    "state_snapshot",
            "state":   None,
            "message": "Incident not found",
        })
        return

    # Build a partial snapshot from the Pydantic incident model
    snapshot: dict = {
        "incident_id":      incident.id,
        "severity":         incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
        "status":           incident.status.value   if hasattr(incident.status,   "value") else str(incident.status),
        "incident_brief":   incident.brief or "",
        "root_cause":       incident.root_cause,
        "confidence_score": incident.confidence_score,
        "affected_services":incident.affected_services,
    }
    await ws.send_json({"type": "state_snapshot", "state": snapshot})
    logger.debug("Sent state_snapshot  incident=%s (from memory)", incident_id)


async def _handle_approval(
    ws:          WebSocket,
    incident_id: str,
    data:        dict,
) -> None:
    """Forward the operator's approval decision to the orchestrator."""
    from main import get_orchestrator  # deferred to avoid circular import

    orchestrator = get_orchestrator()
    if orchestrator:
        await orchestrator.submit_approval(
            incident_id=incident_id,
            approved=bool(data.get("approved", False)),
            notes=str(data.get("notes", "")),
        )

    await ws.send_json({
        "type":     "approval_received",
        "approved": data.get("approved"),
    })
    logger.info(
        "Approval %s recorded  incident=%s",
        "granted" if data.get("approved") else "rejected",
        incident_id,
    )
