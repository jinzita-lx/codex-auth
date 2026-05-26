from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .utils import format_epoch, load_json, pct, pct_left


@dataclass
class UsageSummary:
    status: str = "unknown"
    plan: str = "-"
    five_h_used: str = "-"
    five_h_left: str = "-"
    five_h_reset_short: str = "-"
    five_h_reset_full: str = "-"
    seven_d_used: str = "-"
    seven_d_left: str = "-"
    seven_d_reset_short: str = "-"
    seven_d_reset_full: str = "-"
    credits_balance: str = "-"
    reset_credits: str = "-"

    @classmethod
    def empty(cls, status: str) -> "UsageSummary":
        return cls(status=status)


def _request_json(url: str, token: str, account_id: str = "") -> Tuple[int, Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=15) as response:
            code = response.getcode()
            body = response.read()
    except HTTPError as exc:
        code = exc.code
        body = exc.read()
    except (OSError, URLError):
        return 0, {}

    try:
        import json

        data = json.loads(body.decode("utf-8"))
    except Exception:
        data = {}
    return code, data if isinstance(data, dict) else {}


def fetch_usage(profile_path: Path) -> UsageSummary:
    if not profile_path.exists():
        return UsageSummary.empty("missing")

    data = load_json(profile_path)
    token = data.get("OPENAI_API_KEY") or data.get("tokens", {}).get("access_token") or ""
    account_id = data.get("tokens", {}).get("account_id") or ""
    if not token:
        return UsageSummary.empty("missing")

    if data.get("OPENAI_API_KEY"):
        code, _ = _request_json("https://api.openai.com/v1/models", str(token))
        if code == 200:
            return UsageSummary(status="ok", plan="api-key")
        if code in (401, 403):
            return UsageSummary.empty("unusable")
        return UsageSummary.empty("error")

    code, body = _request_json(
        "https://chatgpt.com/backend-api/wham/usage", str(token), str(account_id)
    )
    if code in (401, 403):
        return UsageSummary.empty("unusable")
    if code != 200:
        return UsageSummary.empty("error")

    rate_limit = body.get("rate_limit") or {}
    status = "ok"
    if (
        rate_limit.get("allowed") is False
        or rate_limit.get("limit_reached") is True
        or body.get("rate_limit_reached_type") is not None
    ):
        status = "limited"

    primary = rate_limit.get("primary_window") or {}
    secondary = rate_limit.get("secondary_window") or {}
    credits = body.get("credits") or {}
    reset_credits = body.get("rate_limit_reset_credits") or {}

    balance = "-"
    if credits.get("unlimited") is True:
        balance = "unlimited"
    elif credits.get("balance") is not None:
        balance = str(credits["balance"])

    return UsageSummary(
        status=status,
        plan=str(body.get("plan_type") or "-"),
        five_h_used=pct(primary.get("used_percent")),
        five_h_left=pct_left(primary.get("used_percent")),
        five_h_reset_short=format_epoch(primary.get("reset_at"), "%m-%d %H:%M"),
        five_h_reset_full=format_epoch(primary.get("reset_at"), "%Y-%m-%d %H:%M:%S %Z"),
        seven_d_used=pct(secondary.get("used_percent")),
        seven_d_left=pct_left(secondary.get("used_percent")),
        seven_d_reset_short=format_epoch(secondary.get("reset_at"), "%m-%d %H:%M"),
        seven_d_reset_full=format_epoch(secondary.get("reset_at"), "%Y-%m-%d %H:%M:%S %Z"),
        credits_balance=balance,
        reset_credits=str(reset_credits.get("available_count", "-")),
    )
