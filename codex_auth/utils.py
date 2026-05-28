import base64
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict


PROFILE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_name(name: str) -> None:
    if not name:
        raise ValueError("profile name is required")
    if not PROFILE_RE.match(name):
        raise ValueError(
            "profile name may only contain letters, numbers, dot, underscore, and hyphen"
        )
    if name in (".", ".."):
        raise ValueError("invalid profile name")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_text_secure(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def profile_identity(path: Path) -> str:
    data = load_json(path)
    if data.get("OPENAI_API_KEY"):
        return "<api-key>"
    token = (
        data.get("tokens", {}).get("id_token")
        or data.get("tokens", {}).get("idToken")
        or data.get("id_token")
        or ""
    )
    payload = jwt_payload(token) if isinstance(token, str) else {}
    for key in ("email", "preferred_username", "name", "sub"):
        value = payload.get(key)
        if value:
            return str(value)
    profile = payload.get("https://api.openai.com/profile")
    if isinstance(profile, dict) and profile.get("email"):
        return str(profile["email"])
    for key in ("email", "account"):
        if data.get(key):
            return str(data[key])
    account_id = data.get("tokens", {}).get("account_id")
    return str(account_id) if account_id else ""


def profile_identity_key(path: Path) -> str:
    data = load_json(path)
    if data.get("OPENAI_API_KEY"):
        raw = str(data["OPENAI_API_KEY"]).encode("utf-8")
        return "api-key:" + base64.b64encode(raw).decode("ascii")
    token = (
        data.get("tokens", {}).get("id_token")
        or data.get("tokens", {}).get("idToken")
        or data.get("id_token")
        or ""
    )
    payload = jwt_payload(token) if isinstance(token, str) else {}
    auth = payload.get("https://api.openai.com/auth")
    if isinstance(auth, dict) and auth.get("chatgpt_account_id"):
        return str(auth["chatgpt_account_id"])
    for key in ("email", "sub"):
        if payload.get(key):
            return str(payload[key])
    for key in ("account_id",):
        value = data.get("tokens", {}).get(key)
        if value:
            return str(value)
    for key in ("email", "account"):
        if data.get(key):
            return str(data[key])
    return ""


def format_epoch(epoch: Any, fmt: str) -> str:
    try:
        value = int(epoch)
    except (TypeError, ValueError):
        return "-"
    try:
        return dt.datetime.fromtimestamp(value).astimezone().strftime(fmt)
    except Exception:
        return "-"


def pct(value: Any) -> str:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "-"
    number = max(0, min(100, number))
    return f"{number}%"


def pct_left(value: Any) -> str:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "-"
    number = max(0, min(100, 100 - number))
    return f"{number}%"
