from __future__ import annotations

import argparse
import json

from agentplatform import Client

from app.config import settings


def _session_id(name: str | None) -> str:
    return name.rsplit("/", 1)[-1] if name else ""


def _session_payload(session: object) -> dict[str, object]:
    state = getattr(session, "session_state", None)
    payload: dict[str, object] = {
        "session_id": _session_id(getattr(session, "name", None)),
        "session_name": getattr(session, "name", None),
        "user_id": getattr(session, "user_id", None),
        "state": state or {},
        "create_time": getattr(session, "create_time", None),
        "update_time": getattr(session, "update_time", None),
        "expire_time": getattr(session, "expire_time", None),
    }
    if not state:
        payload["message"] = "Session exists, but no explicit session state has been stored."
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="user-123")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--session-id", help="Numeric managed session ID")
    selection.add_argument("--list", action="store_true", help="List sessions for the user")
    args = parser.parse_args()
    if not settings.project or not settings.session_resource_id:
        raise SystemExit("Configure project and Agent Platform Sessions ID")

    client = Client(
        project=settings.project,
        location=settings.location,
    )
    engine_name = (
        f"projects/{settings.project}/locations/{settings.location}"
        f"/reasoningEngines/{settings.session_resource_id}"
    )
    sessions = [
        session
        for session in client.agent_engines.sessions.list(name=engine_name)
        if session.user_id == args.user_id
    ]

    if args.list:
        print(json.dumps([_session_payload(session) for session in sessions], indent=2, default=str))
        return

    session = next(
        (session for session in sessions if _session_id(session.name) == args.session_id), None
    )
    if session is None:
        available = ", ".join(_session_id(item.name) for item in sessions) or "none"
        raise SystemExit(
            f"Session {args.session_id!r} was not found for user {args.user_id!r}. "
            f"Available session IDs: {available}. Run with --list for details."
        )

    print(json.dumps(_session_payload(session), indent=2, default=str))


if __name__ == "__main__":
    main()
