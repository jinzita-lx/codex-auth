import getpass
import sys
from typing import List, Tuple

from .colors import Palette
from .store import AuthStore
from .usage import UsageSummary, fetch_usage
from .ui import print_profile_block, print_summary_header, print_summary_line
from .utils import profile_identity, validate_name


USAGE = """Usage:
  codex-auth login <name> [--replace] [codex-login-options...]
                                Login a new account without logging out the current one
  codex-auth login-api          Interactively create an API-key provider profile
  codex-auth save [--with-config] <name>
                                Save current Codex auth.json as a named profile
  codex-auth switch [--no-restart-app-server] <name>
                                Switch ~/.codex/auth.json to a saved profile
  codex-auth list [--no-check] List saved profiles as a concise account summary
  codex-auth check [name|--all]
                                Check whether saved profile auth is usable and show 5h/7d usage
  codex-auth rename <old> <new>
                                Rename a saved profile
  codex-auth current           Show active profile marker, identity, usability, 5h/7d usage, and reset time
  codex-auth status [name]     Show detailed status for active or named profile
  codex-auth remove <name>     Delete a saved profile
  codex-auth path              Show auth/profile paths

Examples:
  codex-auth save work
  codex-auth login personal
  codex-auth login-api
  codex-auth switch work

Color:
  CODEX_AUTH_COLOR=auto|always|never
"""


def main(argv: List[str] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    store = AuthStore()
    palette = Palette()

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0

    cmd = argv.pop(0)
    try:
        if cmd in ("path", "paths"):
            store.print_paths()
            return 0

        with store.lock():
            if cmd in ("login", "login-as", "add"):
                if not argv:
                    raise RuntimeError("profile name is required")
                return store.login_new_profile(argv[0], argv[1:])
            if cmd in ("login-api", "api-login"):
                _require_count(argv, 0, "login-api")
                options = _prompt_api_login(store)
                if not options:
                    return 0
                store.login_api_profile(**options)
                return 0
            if cmd == "save":
                name, with_config = _parse_save_args(argv)
                store.save_as(name, with_config=with_config)
                return 0
            if cmd in ("switch", "use"):
                name, restart_app_server = _parse_switch_args(argv)
                store.switch_to(name, restart_app_server=restart_app_server)
                return 0
            if cmd in ("list", "ls"):
                _list_profiles(store, palette, argv)
                return 0
            if cmd == "check":
                _check_profiles(store, palette, argv)
                return 0
            if cmd == "current":
                _require_count(argv, 0, "current")
                _show_current(store, palette, run_codex_status=True)
                return 0
            if cmd == "status":
                _show_status(store, palette, argv, run_codex_status=not argv)
                return 0
            if cmd in ("remove", "rm", "delete"):
                _require_count(argv, 1, "remove")
                store.remove_profile(argv[0])
                return 0
            if cmd in ("rename", "mv"):
                _require_count(argv, 2, "rename")
                store.rename_profile(argv[0], argv[1])
                return 0
    except (RuntimeError, ValueError) as exc:
        print(f"codex-auth: {exc}", file=sys.stderr)
        return 1

    print(USAGE, file=sys.stderr, end="")
    print(f"codex-auth: unknown command: {cmd}", file=sys.stderr)
    return 1


def _require_count(argv: List[str], expected: int, cmd: str) -> None:
    if len(argv) != expected:
        raise RuntimeError(f"{cmd} expects {expected} argument(s)")


def _parse_switch_args(argv: List[str]) -> Tuple[str, bool]:
    restart_app_server = True
    names = []
    for arg in argv:
        if arg == "--no-restart-app-server":
            restart_app_server = False
        else:
            names.append(arg)
    if len(names) != 1:
        raise RuntimeError("switch expects 1 profile name")
    return names[0], restart_app_server


def _parse_save_args(argv: List[str]) -> Tuple[str, bool]:
    with_config = False
    names = []
    for arg in argv:
        if arg == "--with-config":
            with_config = True
        else:
            names.append(arg)
    if len(names) != 1:
        raise RuntimeError("save expects 1 profile name")
    return names[0], with_config


def _prompt_api_login(store: AuthStore) -> dict:
    name = _prompt_required("Profile name")
    validate_name(name)
    exists = store.profile_path(name).exists() or store.profile_config_path(name).exists()
    replace = False
    if exists:
        replace = _prompt_bool(f'Profile "{name}" exists. Replace?', False)
        if not replace:
            print("Aborted.")
            return {}

    provider = _prompt_default("Provider name", "PeachCode")
    base_url = _prompt_default("Base URL", "https://cli.rhinelab.com.cn")
    api_key = _prompt_secret("API key")
    model = _prompt_default("Model", "gpt-5.5")

    review_model = model
    reasoning_effort = "xhigh"
    wire_api = "responses"
    requires_openai_auth = True
    disable_response_storage = True
    network_access = "enabled"
    context_window = 1000000
    compact_token_limit = 900000

    if _prompt_bool("Customize advanced settings?", False):
        review_model = _prompt_default("Review model", review_model)
        reasoning_effort = _prompt_default("Reasoning effort", reasoning_effort)
        wire_api = _prompt_default("Wire API", wire_api)
        requires_openai_auth = _prompt_bool("Requires OpenAI auth?", requires_openai_auth)
        disable_response_storage = _prompt_bool(
            "Disable response storage?", disable_response_storage
        )
        network_access = _prompt_default("Network access", network_access)
        context_window = _prompt_int("Context window", context_window)
        compact_token_limit = _prompt_int("Auto compact token limit", compact_token_limit)

    return {
        "name": name,
        "api_key": api_key,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "review_model": review_model,
        "reasoning_effort": reasoning_effort,
        "wire_api": wire_api,
        "requires_openai_auth": requires_openai_auth,
        "disable_response_storage": disable_response_storage,
        "network_access": network_access,
        "context_window": context_window,
        "compact_token_limit": compact_token_limit,
        "replace": replace,
    }


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.", file=sys.stderr)


def _prompt_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_secret(label: str) -> str:
    while True:
        value = getpass.getpass(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.", file=sys.stderr)


def _prompt_bool(label: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("Please answer y or n.", file=sys.stderr)


def _prompt_int(label: str, default: int) -> int:
    while True:
        value = input(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print(f"{label} must be an integer.", file=sys.stderr)
            continue
        if parsed > 0:
            return parsed
        print(f"{label} must be positive.", file=sys.stderr)


def _list_profiles(store: AuthStore, palette: Palette, argv: List[str]) -> None:
    check = True
    if argv:
        if argv[0] == "--no-check":
            check = False
            argv = argv[1:]
        elif argv[0] == "--check":
            argv = argv[1:]
        else:
            raise RuntimeError(f"unknown list option: {argv[0]}")
    if argv:
        raise RuntimeError("too many list arguments")

    profiles = store.profiles()
    if not profiles:
        print("No saved Codex auth profiles.")
        return

    warning = store.active_marker_warning()
    if warning:
        print(f"codex-auth: {warning}", file=sys.stderr)

    active = store.current_profile_name()
    print_summary_header(palette)
    for path in profiles:
        name = path.stem
        identity = profile_identity(path) or "<unknown>"
        summary = fetch_usage(path) if check else UsageSummary(status="unchecked")
        marker = "*" if name == active else " "
        print_summary_line(palette, marker, name, identity, summary)


def _check_profiles(store: AuthStore, palette: Palette, argv: List[str]) -> None:
    if not argv or argv[0] == "--all":
        _list_profiles(store, palette, ["--check"])
        return
    if len(argv) != 1:
        raise RuntimeError("too many check arguments")
    name = argv[0]
    validate_name(name)
    path = store.profile_path(name)
    if not path.exists():
        raise RuntimeError(f"profile not found: {name}")
    marker = "*" if name == store.current_profile_name() else " "
    print_profile_block(
        palette,
        marker,
        name,
        profile_identity(path) or "<unknown>",
        fetch_usage(path),
        "short",
    )


def _show_status(
    store: AuthStore,
    palette: Palette,
    argv: List[str],
    run_codex_status: bool,
) -> None:
    if len(argv) > 1:
        raise RuntimeError("too many status arguments")
    if argv:
        _show_named_status(store, palette, argv[0])
        return
    _show_current(store, palette, run_codex_status)


def _show_named_status(store: AuthStore, palette: Palette, name: str) -> None:
    validate_name(name)
    path = store.profile_path(name)
    if not path.exists():
        raise RuntimeError(f"profile not found: {name}")
    marker = "*" if name == store.current_profile_name() else " "
    print_profile_block(
        palette,
        marker,
        name,
        profile_identity(path) or "<unknown>",
        fetch_usage(path),
        "full",
    )


def _show_current(store: AuthStore, palette: Palette, run_codex_status: bool) -> None:
    warning = store.active_marker_warning()
    if warning:
        print(f"codex-auth: {warning}", file=sys.stderr)

    active = store.current_profile_name()
    if not active:
        marker = store.active_name()
        if marker:
            print(f"Active profile marker: {marker} (stale)")
        if store.auth_file.exists():
            print_profile_block(
                palette,
                " ",
                "<auth.json>",
                profile_identity(store.auth_file) or "<unknown>",
                fetch_usage(store.auth_file),
                "full",
            )
            if run_codex_status:
                store.codex_login_status()
            return
        print("Active profile marker: <none>")
        print("Status:   unknown")
        if run_codex_status:
            store.codex_login_status()
        return

    path = store.profile_path(active)
    print_profile_block(
        palette,
        "*",
        active,
        profile_identity(path) or "<unknown>",
        fetch_usage(path),
        "full",
    )
    if run_codex_status:
        store.codex_login_status()
