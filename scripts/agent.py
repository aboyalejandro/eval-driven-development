"""Headless agent runner — HTTP adapter for AgentOS REST API."""

import os
import uuid
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv

load_dotenv()

AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:7777")
AGENT_ID = os.getenv("AGENT_ID", "substack-author-agent")


async def create_agent(
    session_id: str,
    run_id: str,
    context: dict | None = None,
):
    """HTTP proxy to a running AgentOS server.

    Targets: POST {AGENT_BASE_URL}/agents/{AGENT_ID}/runs
    Response shape: {"content": "...", "run_id": "...", "session_id": "...", "status": "COMPLETED"}

    OTEL is emitted by the agent server itself (openinference-instrumentation-agno).
    No instrumentation needed here — traces land in Opik via the server's exporter.

    Context: AgentOS has no native context field. For this agent type (conversational,
    no page/tenant injection), context keys are folded into the message as a natural
    qualifier — this matches how production users phrase context-bearing requests.
    """

    class AgentProxy:
        def __init__(self):
            self.name = f"sim-{run_id}-{AGENT_ID}"
            self._session_id = session_id
            self._context = context or {}

        async def arun(self, message: str):
            full_message = message
            if self._context:
                qualifier = ", ".join(f"{k}: {v}" for k, v in self._context.items())
                full_message = f"{message} ({qualifier})"

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{AGENT_BASE_URL}/agents/{AGENT_ID}/runs",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={"message": full_message, "session_id": self._session_id},
                )
                resp.raise_for_status()
                data = resp.json()

            return SimpleNamespace(content=data.get("content", ""))

    return AgentProxy()


async def run_scenario(
    message: str,
    run_id: str,
    context: dict | None = None,
    followups: list[str] | None = None,
) -> str:
    session_id = f"sim-{run_id}-{uuid.uuid4().hex[:6]}"
    agent = await create_agent(session_id, run_id, context=context)

    response = await agent.arun(message)
    content = response.content if hasattr(response, "content") else str(response)

    for followup in followups or []:
        response = await agent.arun(followup)
        content = response.content if hasattr(response, "content") else str(response)

    return content
