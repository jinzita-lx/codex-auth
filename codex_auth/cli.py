import sys
from typing import List

from .colors import Palette
from .store import AuthStore
from .usage import UsageSummary, fetch_usage
from .ui import print_profile_block, print_summary_header, print_summary_line
from .utils import profile_identity, validate_name


USAGE = """Usage:
  codex-auth login <name> [--replace] [codex-login-options...]
                                Login a new account without logging out the current one
  codex-auth save <name>       Save current Codex auth.json as a named profile
  codex-auth switch <name>     Switch ~/.codex/auth.json to a saved profile
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
            if cmd == "save":
                _require_count(argv, 1, "save")
                store.save_as(argv[0])
                return 0
            if cmd in ("switch", "use"):
                _require_count(argv, 1, "switch")
                store.switch_to(argv[0])
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

    active = store.active_name()
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
    marker = "*" if name == store.active_name() else " "
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
    marker = "*" if name == store.active_name() else " "
    print_profile_block(
        palette,
        marker,
        name,
        profile_identity(path) or "<unknown>",
        fetch_usage(path),
        "full",
    )


def _show_current(store: AuthStore, palette: Palette, run_codex_status: bool) -> None:
    active = store.active_name()
    if not active:
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
