"""Headless HTTP adapter for the agent under test. See scripts/setup/CLAUDE.md + PREREQUISITES.md."""

import importlib
import sys
import uuid
from types import SimpleNamespace

import httpx

from shared.settings import settings


def _load_adapter():
    """Load create_agent from AGENT_ADAPTER if set, else return None."""
    adapter_path = settings.agent_adapter
    if not adapter_path:
        return None
    mod_path, fn_name = adapter_path.rsplit(":", 1)
    # Ensure repo root is on sys.path so _local.* imports resolve.
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    mod = importlib.import_module(mod_path)
    return getattr(mod, fn_name)


_adapter_create_agent = _load_adapter()


async def _default_create_agent(
    session_id: str,
    run_id: str,
    context: dict | None = None,
):
    """Return an AgentProxy using the generic JSON contract."""
    if not settings.agent_endpoint:
        raise RuntimeError(
            "AGENT_ENDPOINT is not set. Configure it in .env (see .env.example)."
        )

    class AgentProxy:
        def __init__(self) -> None:
            self.name = f"sim-{run_id}-{settings.agent_name}"
            self._session_id = session_id
            self._context = context or {}

        async def arun(self, message: str) -> SimpleNamespace:
            full_message = message
            if self._context:
                qualifier = ", ".join(f"{k}: {v}" for k, v in self._context.items())
                full_message = f"{message} ({qualifier})"

            headers = {"Content-Type": "application/json"}
            if settings.agent_auth:
                headers["Authorization"] = settings.agent_auth

            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    settings.agent_endpoint,
                    headers=headers,
                    json={"message": full_message, "session_id": self._session_id},
                )
                resp.raise_for_status()
                data = resp.json()

            return SimpleNamespace(content=data.get("content", ""))

    return AgentProxy()


async def create_agent(
    session_id: str,
    run_id: str,
    context: dict | None = None,
):
    """Return an object with `arun(message)` that calls the agent over HTTP.

    Uses AGENT_ADAPTER if set, otherwise the generic JSON default.
    """
    if _adapter_create_agent:
        return await _adapter_create_agent(session_id, run_id, context)
    return await _default_create_agent(session_id, run_id, context)


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
