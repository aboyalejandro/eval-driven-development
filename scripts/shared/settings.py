"""Centralised environment variable access.

All env var reads in the framework go through this module. Import the
`settings` singleton — never call `os.getenv` or `os.environ` directly
in library code.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Read-only snapshot of required env vars, taken at import time."""

    # Opik connection
    opik_url: str = field(default_factory=lambda: os.getenv("OPIK_URL", ""))
    opik_api_key: str = field(default_factory=lambda: os.getenv("OPIK_API_KEY", ""))
    opik_workspace: str = field(default_factory=lambda: os.getenv("OPIK_WORKSPACE", ""))

    # Eval project
    eval_project: str = field(default_factory=lambda: os.getenv("EVAL_PROJECT", "Testing"))

    # Agent HTTP target
    agent_endpoint: str = field(default_factory=lambda: os.getenv("AGENT_ENDPOINT", ""))
    agent_auth: str = field(default_factory=lambda: os.getenv("AGENT_AUTH", ""))
    agent_name: str = field(default_factory=lambda: os.getenv("AGENT_NAME", "agent"))
    agent_adapter: str = field(default_factory=lambda: os.getenv("AGENT_ADAPTER", ""))


settings = Settings()
