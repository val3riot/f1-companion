from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .config import load_dotenv


def _b64_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())


def decode_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Il valore non sembra un JWT: servono 3 parti separate da punto")
    return {
        "header": _b64_json(parts[0]),
        "payload": _b64_json(parts[1]),
        "signature_bytes": len(parts[2]),
    }


def token_from_login_session(value: str) -> str | None:
    try:
        session = json.loads(unquote(value))
    except json.JSONDecodeError:
        return None
    token = session.get("data", {}).get("subscriptionToken")
    return token if isinstance(token, str) and token else None


def _time(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _expired(value: Any) -> bool | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.now(timezone.utc).timestamp() >= value


def explain_token(name: str, token: str) -> dict[str, Any]:
    decoded = decode_jwt(token)
    payload = decoded["payload"]
    return {
        "name": name,
        "algorithm": decoded["header"].get("alg"),
        "key_id": decoded["header"].get("kid"),
        "issuer": payload.get("iss"),
        "subscription_status": payload.get("SubscriptionStatus"),
        "subscription": payload.get("Subscription"),
        "subscribed_product": payload.get("SubscribedProduct"),
        "subscriber_id_present": bool(payload.get("SubscriberId")),
        "entitlements": payload.get("ents"),
        "issued_at": _time(payload.get("iat")),
        "expires_at": _time(payload.get("exp")),
        "expired": _expired(payload.get("exp")),
        "usable_for_signalr": (
            payload.get("SubscriptionStatus") == "active"
            and bool(payload.get("SubscribedProduct"))
        ),
    }


def read_env(path: str) -> dict[str, str]:
    load_dotenv(path)
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ispeziona token F1TV senza stampare segreti.",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="File env da leggere, default: .env",
    )
    parser.add_argument(
        "--token",
        help="JWT diretto da ispezionare",
    )
    parser.add_argument(
        "--login-session",
        help="Valore URL-encoded del cookie login-session",
    )
    args = parser.parse_args()

    env = read_env(args.env)
    candidates: list[tuple[str, str]] = []
    if args.token:
        candidates.append(("argomento --token", args.token))
    if args.login_session:
        token = token_from_login_session(args.login_session)
        if token:
            candidates.append(("argomento --login-session.subscriptionToken", token))
    if env.get("F1_SIGNALR_AUTH_TOKEN"):
        candidates.append(("F1_SIGNALR_AUTH_TOKEN", env["F1_SIGNALR_AUTH_TOKEN"]))
    if env.get("F1_SIGNALR_LOGIN_SESSION"):
        token = token_from_login_session(env["F1_SIGNALR_LOGIN_SESSION"])
        if token:
            candidates.append(("F1_SIGNALR_LOGIN_SESSION.subscriptionToken", token))

    if not candidates:
        print(
            "Nessun token trovato. Imposta F1_SIGNALR_LOGIN_SESSION o "
            "F1_SIGNALR_AUTH_TOKEN in .env, oppure passa --login-session/--token."
        )
        return

    for name, token in candidates:
        try:
            info = explain_token(name, token)
        except Exception as exc:
            print(json.dumps({"name": name, "error": str(exc)}, indent=2))
            continue
        print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
