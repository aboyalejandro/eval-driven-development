"""Headless agent runner — HTTP adapter.

The framework assumes the agent under test is reachable over HTTP. This adapter
is a starting template: edit `arun()` if your agent's request/response shape
differs from the default contract below.

Default contract (truly generic — nothing runtime-specific):
    POST {AGENT_ENDPOINT}
    Content-Type: application/x-www-form-urlencoded
    body: message=<str>
    response: JSON with `content` field containing the assistant reply

The framework mints `self._session_id` on the AgentProxy for multi-turn scenarios.
If your agent supports session continuity (Agno/AgentOS uses `session_id`, OpenAI
Assistants uses `thread_id`, etc.), transmit it from `self._session_id` inside
your customised arun(). Same goes for streaming control, auth schemes, structured
context, and any other runtime-specific fields — adapt arun() in your fork.

The agent is responsible for its own OTEL → Opik tracing. This adapter does not
instrument the agent runtime; it only invokes the endpoint and relays the text
response. See `PREREQUISITES.md` for the full integration contract.
"""

import os
import uuid
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv

load_dotenv()

AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")
AGENT_AUTH = os.getenv("AGENT_AUTH")  # optional, sent as Authorization header
AGENT_NAME = os.getenv("AGENT_NAME", "agent")  # informational only


async def create_agent(
    session_id: str,
    run_id: str,
    context: dict | None = None,
):
    """Return an object with `arun(message)` that calls the agent over HTTP."""
    if not AGENT_ENDPOINT:
        raise RuntimeError(
            "AGENT_ENDPOINT is not set. Configure it in .env (see .env.example)."
        )

    class AgentProxy:
        def __init__(self):
            self.name = f"sim-{run_id}-{AGENT_NAME}"
            self._session_id = session_id
            self._context = context or {}

        async def arun(self, message: str):
            full_message = message
            if self._context:
                qualifier = ", ".join(f"{k}: {v}" for k, v in self._context.items())
                full_message = f"{message} ({qualifier})"

            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if AGENT_AUTH:
                headers["Authorization"] = AGENT_AUTH

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    AGENT_ENDPOINT,
                    headers=headers,
                    data={"message": full_message},
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
