"""Register deterministic code metrics on an Opik project.

Usage:
    python -m metrics.register --project <name> --dry-run
    python -m metrics.register --project <name>
    python -m metrics.register --project <name> --enable
"""

import argparse
import json
import sys

sys.path.insert(0, ".")

from metrics.registry import ALL_METRICS, build_payload
from shared.opik_client import OpikClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Opik project name.")
    parser.add_argument(
        "--enable", action="store_true", help="Register with enabled=True."
    )
    parser.add_argument("--sampling-rate", type=float, default=1.0)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print payloads without POSTing."
    )
    args = parser.parse_args()

    client = OpikClient()
    project_id = client.get_project_id(args.project)

    existing_by_name: dict[str, str] = {}
    for e in client.get_evaluators().get("content", []):
        project_ids = e.get("project_ids") or (
            [e["project_id"]] if e.get("project_id") else []
        )
        if project_id in project_ids:
            existing_by_name[e["name"]] = e["id"]

    for metric_cls in ALL_METRICS:
        payload = build_payload(
            metric_cls,
            project_id=project_id,
            enabled=args.enable,
            sampling_rate=args.sampling_rate,
        )
        name = payload["name"]
        action = "PATCH" if name in existing_by_name else "POST"
        if args.dry_run:
            preview = {k: v for k, v in payload.items() if k != "code"}
            print(f"[dry-run] {action} {name}")
            print(json.dumps(preview, indent=2))
            print(f"  code.arguments = {payload['code']['arguments']}")
            print(f"  code.metric    = <{len(payload['code']['metric'])} bytes>")
            continue
        if action == "PATCH":
            client.update_evaluator(existing_by_name[name], payload)
        else:
            client._request("POST", "/v1/private/automations/evaluators", json=payload)
        print(f"{action} {name} -> ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
