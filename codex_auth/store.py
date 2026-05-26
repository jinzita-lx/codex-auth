import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from .utils import profile_identity_key, validate_name, write_text_secure


class AuthStore:
    def __init__(self) -> None:
        self.codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
        self.auth_file = self.codex_home / "auth.json"
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

    def profiles(self) -> List[Path]:
        self.ensure_profiles_dir()
        return sorted(self.profiles_dir.glob("*.json"))

    def active_name(self) -> str:
        try:
            return self.active_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def set_active(self, name: str) -> None:
        validate_name(name)
        write_text_secure(self.active_file, f"{name}\n")

    def require_auth(self) -> None:
        if not self.auth_file.exists():
            raise RuntimeError(f"no auth.json found at {self.auth_file}; run codex login first")

    def save_as(self, name: str) -> None:
        dest = self.profile_path(name)
        self.require_auth()
        self.ensure_profiles_dir()
        shutil.copy2(self.auth_file, dest)
        dest.chmod(0o600)
        self.set_active(name)
        print(f"Saved current Codex auth as profile: {name}")

    def save_current_to_active_if_possible(self) -> None:
        if not self.auth_file.exists():
            return
        name = self.active_name()
        if not name:
            return
        validate_name(name)
        dest = self.profile_path(name)
        if dest.exists():
            current_key = profile_identity_key(self.auth_file)
            dest_key = profile_identity_key(dest)
            if current_key and dest_key and current_key != dest_key:
                print(
                    f'codex-auth: skip autosave for active profile "{name}": '
                    "current auth belongs to a different account",
                    file=sys.stderr,
                )
                return
        shutil.copy2(self.auth_file, dest)
        dest.chmod(0o600)

    def switch_to(self, name: str) -> None:
        src = self.profile_path(name)
        if not src.exists():
            raise RuntimeError(f"profile not found: {name}")
        self.save_current_to_active_if_possible()
        tmp = self.codex_home / f".auth.json.tmp.{os.getpid()}"
        shutil.copy2(src, tmp)
        tmp.chmod(0o600)
        tmp.replace(self.auth_file)
        self.set_active(name)
        print(f"Switched Codex auth profile to: {name}")
        self.codex_login_status()

    def remove_profile(self, name: str) -> None:
        path = self.profile_path(name)
        if not path.exists():
            raise RuntimeError(f"profile not found: {name}")
        path.unlink()
        if self.active_name() == name:
            try:
                self.active_file.unlink()
            except FileNotFoundError:
                pass
        print(f"Removed Codex auth profile: {name}")

    def rename_profile(self, old_name: str, new_name: str) -> None:
        old_path = self.profile_path(old_name)
        new_path = self.profile_path(new_name)
        if not old_path.exists():
            raise RuntimeError(f"profile not found: {old_name}")
        if new_path.exists():
            raise RuntimeError(f"target profile already exists: {new_name}")

        active = self.active_name()
        if active == old_name:
            self.save_current_to_active_if_possible()

        old_path.rename(new_path)
        new_path.chmod(0o600)
        if active == old_name:
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

        previous_active = self.active_name()
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
