import json
import os
import signal
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from .utils import profile_identity_key, validate_name, write_text_secure


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_key(value: str) -> str:
    if value and all(char.isalnum() or char in ("_", "-") for char in value):
        return value
    return json.dumps(value)


class AuthStore:
    def __init__(self) -> None:
        self.codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
        self.auth_file = self.codex_home / "auth.json"
        self.config_file = self.codex_home / "config.toml"
        self.profiles_dir = self.codex_home / "auth-profiles"
        self.active_file = self.profiles_dir / ".active"
        self.lock_dir = self.profiles_dir / ".lock"

    def ensure_profiles_dir(self) -> None:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.chmod(0o700)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.ensure_profiles_dir()
        acquired = False
        for _ in range(100):
            try:
                self.lock_dir.mkdir()
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.1)
        if not acquired:
            raise RuntimeError(f"could not acquire lock: {self.lock_dir}")
        try:
            yield
        finally:
            try:
                self.lock_dir.rmdir()
            except OSError:
                pass

    def profile_path(self, name: str) -> Path:
        validate_name(name)
        return self.profiles_dir / f"{name}.json"

    def profile_config_path(self, name: str) -> Path:
        validate_name(name)
        return self.profiles_dir / f"{name}.config.toml"

    def profiles(self) -> List[Path]:
        self.ensure_profiles_dir()
        return sorted(self.profiles_dir.glob("*.json"))

    def active_name(self) -> str:
        try:
            return self.active_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def current_profile_name(self) -> str:
        """Return the saved profile that currently matches auth.json, if any."""
        current_key = self._identity_key(self.auth_file)
        if not current_key:
            return ""

        marker = self.active_name()
        if marker:
            try:
                marker_path = self.profile_path(marker)
            except ValueError:
                marker_path = None
            if (
                marker_path
                and marker_path.exists()
                and self._identity_key(marker_path) == current_key
            ):
                return marker

        for path in self.profiles():
            if self._identity_key(path) == current_key:
                return path.stem
        return ""

    def active_marker_warning(self) -> str:
        marker = self.active_name()
        if not marker:
            return ""

        current = self.current_profile_name()
        if current == marker:
            return ""

        if not self.auth_file.exists():
            return f'active profile marker "{marker}" is stale: auth.json is missing'
        if current:
            return (
                f'active profile marker "{marker}" is stale: '
                f'current auth.json matches profile "{current}"'
            )
        return (
            f'active profile marker "{marker}" is stale: '
            "current auth.json does not match any saved profile"
        )

    def set_active(self, name: str) -> None:
        validate_name(name)
        write_text_secure(self.active_file, f"{name}\n")

    def require_auth(self) -> None:
        if not self.auth_file.exists():
            raise RuntimeError(f"no auth.json found at {self.auth_file}; run codex login first")

    def save_as(self, name: str, with_config: bool = False) -> None:
        dest = self.profile_path(name)
        self.require_auth()
        self.ensure_profiles_dir()
        shutil.copy2(self.auth_file, dest)
        dest.chmod(0o600)
        if with_config:
            self.save_config_as(name)
        self.set_active(name)
        print(f"Saved current Codex auth as profile: {name}")
        if with_config:
            print(f"Saved current Codex config as profile: {name}")

    def save_config_as(self, name: str) -> None:
        if not self.config_file.exists():
            raise RuntimeError(f"no config.toml found at {self.config_file}")
        dest = self.profile_config_path(name)
        self.ensure_profiles_dir()
        shutil.copy2(self.config_file, dest)
        dest.chmod(0o600)

    def login_api_profile(
        self,
        name: str,
        api_key: str,
        provider: str,
        base_url: str,
        model: str,
        review_model: str,
        reasoning_effort: str,
        wire_api: str,
        requires_openai_auth: bool,
        disable_response_storage: bool,
        network_access: str,
        context_window: int,
        compact_token_limit: int,
        replace: bool,
        restart_app_server: bool = True,
    ) -> None:
        validate_name(name)
        if not api_key:
            raise RuntimeError("API key is required")
        if not provider:
            raise RuntimeError("provider name is required")
        if not base_url:
            raise RuntimeError("base URL is required")
        if context_window <= 0:
            raise RuntimeError("context window must be positive")
        if compact_token_limit <= 0:
            raise RuntimeError("auto compact token limit must be positive")

        auth_dest = self.profile_path(name)
        config_dest = self.profile_config_path(name)
        if (auth_dest.exists() or config_dest.exists()) and not replace:
            raise RuntimeError(f"profile already exists: {name}")

        self.save_current_to_active_if_possible()
        self.save_current_config_to_active_if_possible()
        self.ensure_profiles_dir()

        auth_text = json.dumps(
            {
                "auth_mode": "apikey",
                "OPENAI_API_KEY": api_key,
            },
            indent=2,
        )
        auth_text += "\n"
        config_text = self.api_config_text(
            provider=provider,
            base_url=base_url,
            model=model,
            review_model=review_model,
            reasoning_effort=reasoning_effort,
            wire_api=wire_api,
            requires_openai_auth=requires_openai_auth,
            disable_response_storage=disable_response_storage,
            network_access=network_access,
            context_window=context_window,
            compact_token_limit=compact_token_limit,
        )

        write_text_secure(auth_dest, auth_text)
        write_text_secure(config_dest, config_text)
        write_text_secure(self.auth_file, auth_text)
        write_text_secure(self.config_file, config_text)
        self.set_active(name)

        print(f"Saved API auth profile: {name}")
        print(f"Saved API config profile: {name}")
        if restart_app_server:
            self.restart_codex_app_server()
        self.codex_login_status()

    def api_config_text(
        self,
        provider: str,
        base_url: str,
        model: str,
        review_model: str,
        reasoning_effort: str,
        wire_api: str,
        requires_openai_auth: bool,
        disable_response_storage: bool,
        network_access: str,
        context_window: int,
        compact_token_limit: int,
    ) -> str:
        provider_key = _toml_key(provider)
        return "\n".join(
            [
                f"model_provider = {json.dumps(provider)}",
                f"model = {json.dumps(model)}",
                f"review_model = {json.dumps(review_model)}",
                f"model_reasoning_effort = {json.dumps(reasoning_effort)}",
                f"disable_response_storage = {_toml_bool(disable_response_storage)}",
                f"network_access = {json.dumps(network_access)}",
                f"model_context_window = {context_window}",
                f"model_auto_compact_token_limit = {compact_token_limit}",
                "",
                f"[model_providers.{provider_key}]",
                f"name = {json.dumps(provider)}",
                f"base_url = {json.dumps(base_url)}",
                f"wire_api = {json.dumps(wire_api)}",
                f"requires_openai_auth = {_toml_bool(requires_openai_auth)}",
                "",
            ]
        )

    def save_current_to_active_if_possible(self) -> None:
        if not self.auth_file.exists():
            return
        name = self.current_profile_name() or self.active_name()
        if not name:
            return
        try:
            validate_name(name)
        except ValueError:
            print(
                f'codex-auth: skip autosave for invalid active profile marker "{name}"',
                file=sys.stderr,
            )
            return
        dest = self.profile_path(name)
        if not dest.exists():
            print(
                f'codex-auth: skip autosave for active profile "{name}": profile file is missing',
                file=sys.stderr,
            )
            return

        current_key = self._identity_key(self.auth_file)
        dest_key = self._identity_key(dest)
        if not current_key or not dest_key:
            print(
                f'codex-auth: skip autosave for active profile "{name}": '
                "could not verify account identity",
                file=sys.stderr,
            )
            return
        if current_key != dest_key:
            print(
                f'codex-auth: skip autosave for active profile "{name}": '
                "current auth belongs to a different account",
                file=sys.stderr,
            )
            return
        shutil.copy2(self.auth_file, dest)
        dest.chmod(0o600)

    def save_current_config_to_active_if_possible(self) -> None:
        if not self.config_file.exists():
            return
        name = self.current_profile_name()
        if not name:
            return
        dest = self.profile_config_path(name)
        shutil.copy2(self.config_file, dest)
        dest.chmod(0o600)

    def switch_to(self, name: str, restart_app_server: bool = True) -> None:
        src = self.profile_path(name)
        if not src.exists():
            raise RuntimeError(f"profile not found: {name}")
        self.save_current_to_active_if_possible()
        self.save_current_config_to_active_if_possible()
        tmp = self.codex_home / f".auth.json.tmp.{os.getpid()}"
        shutil.copy2(src, tmp)
        tmp.chmod(0o600)
        tmp.replace(self.auth_file)
        if self.auth_file.read_bytes() != src.read_bytes():
            raise RuntimeError(f"failed to switch auth.json to profile: {name}")
        switched_config = self.apply_profile_config_if_exists(name)
        self.set_active(name)
        print(f"Switched Codex auth profile to: {name}")
        if switched_config:
            print(f"Switched Codex config profile to: {name}")
        if restart_app_server:
            self.restart_codex_app_server()
        self.codex_login_status()

    def apply_profile_config_if_exists(self, name: str) -> bool:
        src = self.profile_config_path(name)
        if not src.exists():
            return False
        tmp = self.codex_home / f".config.toml.tmp.{os.getpid()}"
        shutil.copy2(src, tmp)
        tmp.chmod(0o600)
        tmp.replace(self.config_file)
        if self.config_file.read_bytes() != src.read_bytes():
            raise RuntimeError(f"failed to switch config.toml to profile: {name}")
        return True

    def restart_codex_app_server(self) -> None:
        stopped = self.stop_codex_app_server_processes()
        codex = shutil.which("codex")
        if not codex:
            if stopped:
                print(
                    "Stopped stale Codex app-server, but could not restart it: codex not found",
                    file=sys.stderr,
                )
            return

        log_path = self.codex_home / "log" / "codex-auth-app-server.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            try:
                process = subprocess.Popen(
                    [codex, "app-server", "--listen", "unix://"],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            except OSError as exc:
                print(f"codex-auth: failed to restart Codex app-server: {exc}", file=sys.stderr)
                return

        time.sleep(0.2)
        if process.poll() is None:
            print("Restarted Codex app-server so future sessions reload auth.")
            return
        print(
            f"codex-auth: Codex app-server exited during restart; see {log_path}",
            file=sys.stderr,
        )

    def stop_codex_app_server_processes(self) -> List[int]:
        pids = self.codex_app_server_pids()
        for pid in pids:
            self._kill_pid(pid, signal.SIGTERM)

        deadline = time.time() + 2
        remaining = pids
        while remaining and time.time() < deadline:
            time.sleep(0.1)
            remaining = [pid for pid in remaining if self._pid_exists(pid)]

        for pid in remaining:
            self._kill_pid(pid, signal.SIGKILL)
        return pids

    def codex_app_server_pids(self) -> List[int]:
        pids = []
        own_pid = os.getpid()
        for pid, argv in self._iter_process_argv():
            if pid == own_pid:
                continue
            if self._is_codex_app_server_argv(argv):
                pids.append(pid)
        return pids

    def _iter_process_argv(self) -> Iterator[tuple]:
        proc = Path("/proc")
        if proc.exists():
            for entry in proc.iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    raw = (entry / "cmdline").read_bytes()
                except OSError:
                    continue
                argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
                if argv:
                    yield int(entry.name), argv
            return

        try:
            output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
        except (OSError, subprocess.SubprocessError):
            return
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            try:
                import shlex

                argv = shlex.split(parts[1])
            except ValueError:
                argv = parts[1].split()
            if argv:
                yield int(parts[0]), argv

    def _is_codex_app_server_argv(self, argv: List[str]) -> bool:
        if len(argv) < 3 or Path(argv[0]).name != "codex":
            return False
        if argv[1] != "app-server":
            return False
        if argv[2] == "proxy":
            return True
        return len(argv) >= 4 and argv[2] == "--listen" and argv[3] == "unix://"

    def _kill_pid(self, pid: int, sig: signal.Signals) -> None:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            print(f"codex-auth: no permission to stop process {pid}", file=sys.stderr)

    def _pid_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def remove_profile(self, name: str) -> None:
        path = self.profile_path(name)
        if not path.exists():
            raise RuntimeError(f"profile not found: {name}")
        current = self.current_profile_name()
        path.unlink()
        config_path = self.profile_config_path(name)
        if config_path.exists():
            config_path.unlink()
        if self.active_name() == name or current == name:
            try:
                self.active_file.unlink()
            except FileNotFoundError:
                pass
        print(f"Removed Codex auth profile: {name}")

    def rename_profile(self, old_name: str, new_name: str) -> None:
        old_path = self.profile_path(old_name)
        new_path = self.profile_path(new_name)
        old_config_path = self.profile_config_path(old_name)
        new_config_path = self.profile_config_path(new_name)
        if not old_path.exists():
            raise RuntimeError(f"profile not found: {old_name}")
        if new_path.exists():
            raise RuntimeError(f"target profile already exists: {new_name}")
        if new_config_path.exists():
            raise RuntimeError(f"target config profile already exists: {new_name}")

        active = self.active_name()
        current = self.current_profile_name()
        if active == old_name or current == old_name:
            self.save_current_to_active_if_possible()

        old_path.rename(new_path)
        new_path.chmod(0o600)
        if old_config_path.exists():
            old_config_path.rename(new_config_path)
            new_config_path.chmod(0o600)
        if active == old_name or current == old_name:
            self.set_active(new_name)
        print(f"Renamed Codex auth profile: {old_name} -> {new_name}")

    def login_new_profile(self, name: str, args: List[str]) -> int:
        dest = self.profile_path(name)
        replace = False
        if args and args[0] == "--replace":
            replace = True
            args = args[1:]
        if dest.exists() and not replace:
            raise RuntimeError(f"profile already exists: {name}; use --replace to overwrite it")

        previous_active = self.current_profile_name() or self.active_name()
        self.save_current_to_active_if_possible()

        backup = None
        if self.auth_file.exists():
            backup = self.profiles_dir / f".auth-before-login.{os.getpid()}.{int(time.time())}.json"
            self.auth_file.rename(backup)
            backup.chmod(0o600)

        print(f"Starting Codex login for profile: {name}")
        print("The current auth.json was moved aside locally; codex logout is not used.")

        rc = subprocess.run(["codex", "login", *args]).returncode
        if rc != 0:
            failed_auth = None
            if self.auth_file.exists():
                failed_auth = self.profiles_dir / f".failed-login-auth.{os.getpid()}.{int(time.time())}.json"
                self.auth_file.rename(failed_auth)
                failed_auth.chmod(0o600)
            if backup and backup.exists():
                backup.rename(self.auth_file)
                self.auth_file.chmod(0o600)
                print("Codex login failed; restored previous auth.json.", file=sys.stderr)
            if failed_auth:
                print(f"Partial login auth was kept at: {failed_auth}", file=sys.stderr)
            return rc

        if not self.auth_file.exists():
            if backup and backup.exists():
                backup.rename(self.auth_file)
                self.auth_file.chmod(0o600)
            raise RuntimeError(f"codex login completed but did not create {self.auth_file}; restored previous auth.json")

        shutil.copy2(self.auth_file, dest)
        dest.chmod(0o600)
        self.set_active(name)

        if backup and backup.exists():
            previous_path = self.profile_path(previous_active) if previous_active else None
            backup_key = profile_identity_key(backup)
            previous_key = profile_identity_key(previous_path) if previous_path and previous_path.exists() else ""
            if backup_key and previous_key and backup_key == previous_key:
                backup.unlink()
            else:
                print(f"Previous auth backup kept at: {backup}")

        print(f"Saved new Codex auth as profile: {name}")
        self.codex_login_status()
        return 0

    def codex_login_status(self) -> None:
        sys.stdout.flush()
        subprocess.run(["codex", "login", "status"], check=False)

    def print_paths(self) -> None:
        print(f"CODEX_HOME: {self.codex_home}")
        print(f"auth.json:   {self.auth_file}")
        print(f"profiles:    {self.profiles_dir}")

    def _identity_key(self, path: Path) -> str:
        return profile_identity_key(path) if path.exists() else ""
