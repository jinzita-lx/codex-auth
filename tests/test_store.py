import base64
import contextlib
import io
import json
import os
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auth.store import AuthStore


def _b64url_json(value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _jwt(payload):
    return ".".join([_b64url_json({"alg": "none"}), _b64url_json(payload), "sig"])


def _chatgpt_auth(email, account_id):
    return {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": f"access-{account_id}",
            "refresh_token": f"refresh-{account_id}",
            "account_id": account_id,
            "id_token": _jwt(
                {
                    "email": email,
                    "sub": f"sub-{account_id}",
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": account_id,
                    },
                }
            ),
        },
    }


def _api_key_auth():
    return {
        "auth_mode": "apikey",
        "OPENAI_API_KEY": "sk-test-placeholder",
    }


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


class AuthStoreTests(unittest.TestCase):
    def _store(self, codex_home: str) -> AuthStore:
        with patch.dict(os.environ, {"CODEX_HOME": codex_home}):
            store = AuthStore()
        store.ensure_profiles_dir()
        return store

    def test_switch_from_external_api_key_does_not_overwrite_marked_profile(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            pro = store.profile_path("pro")
            pro_auth = _chatgpt_auth("pro@example.com", "acct-pro")
            _write_json(pro, pro_auth)
            _write_json(store.profile_path("plus"), _chatgpt_auth("plus@example.com", "acct-plus"))
            store.set_active("pro")
            api_key_auth = _api_key_auth()
            api_key_auth["tokens"] = pro_auth["tokens"]
            _write_json(store.auth_file, api_key_auth)
            original_pro = pro.read_bytes()

            self.assertEqual(store.current_profile_name(), "")
            self.assertIn("does not match any saved profile", store.active_marker_warning())

            store.codex_login_status = lambda: None
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                store.switch_to("pro", restart_app_server=False)

            self.assertEqual(pro.read_bytes(), original_pro)
            self.assertEqual(store.current_profile_name(), "pro")
            self.assertEqual(store.active_marker_warning(), "")
            self.assertEqual(json.loads(store.auth_file.read_text())["auth_mode"], "chatgpt")

    def test_current_profile_uses_auth_json_identity_when_marker_is_stale(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            plus_auth = _chatgpt_auth("plus@example.com", "acct-plus")
            _write_json(store.profile_path("pro"), _chatgpt_auth("pro@example.com", "acct-pro"))
            _write_json(store.profile_path("plus"), plus_auth)
            store.set_active("pro")
            _write_json(store.auth_file, plus_auth)

            self.assertEqual(store.current_profile_name(), "plus")
            self.assertIn('matches profile "plus"', store.active_marker_warning())

    def test_save_with_config_and_switch_restores_profile_config(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            pro_auth = _chatgpt_auth("pro@example.com", "acct-pro")
            api_auth = _api_key_auth()
            _write_json(store.auth_file, pro_auth)
            _write_text(store.config_file, 'model_provider = "OpenAI"\n')
            with contextlib.redirect_stdout(io.StringIO()):
                store.save_as("pro", with_config=True)

            _write_json(store.auth_file, api_auth)
            _write_text(
                store.config_file,
                'model_provider = "PeachCode"\n'
                'model = "gpt-5.5"\n'
                '[model_providers.PeachCode]\n'
                'base_url = "https://cli.rhinelab.com.cn"\n',
            )
            with contextlib.redirect_stdout(io.StringIO()):
                store.save_as("peach-api", with_config=True)

            _write_json(store.auth_file, pro_auth)
            _write_text(store.config_file, 'model_provider = "OpenAI"\n')
            store.set_active("pro")

            store.codex_login_status = lambda: None
            with contextlib.redirect_stdout(io.StringIO()):
                store.switch_to("peach-api", restart_app_server=False)

            self.assertEqual(json.loads(store.auth_file.read_text())["auth_mode"], "apikey")
            self.assertIn('model_provider = "PeachCode"', store.config_file.read_text())

            with contextlib.redirect_stdout(io.StringIO()):
                store.switch_to("pro", restart_app_server=False)

            self.assertEqual(json.loads(store.auth_file.read_text())["auth_mode"], "chatgpt")
            self.assertEqual(store.config_file.read_text(), 'model_provider = "OpenAI"\n')

    def test_switch_autosaves_current_config_for_active_profile(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            pro_auth = _chatgpt_auth("pro@example.com", "acct-pro")
            api_auth = _api_key_auth()
            _write_json(store.profile_path("pro"), pro_auth)
            _write_json(store.profile_path("peach-api"), api_auth)
            _write_text(store.profile_config_path("peach-api"), 'model_provider = "PeachCode"\n')
            _write_json(store.auth_file, pro_auth)
            _write_text(store.config_file, 'model_provider = "OpenAI"\n')
            store.set_active("pro")
            store.codex_login_status = lambda: None

            with contextlib.redirect_stdout(io.StringIO()):
                store.switch_to("peach-api", restart_app_server=False)

            self.assertEqual(store.profile_config_path("pro").read_text(), 'model_provider = "OpenAI"\n')
            self.assertIn('model_provider = "PeachCode"', store.config_file.read_text())

    def test_login_api_profile_creates_auth_and_config_profile(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            store.restart_codex_app_server = lambda: None
            store.codex_login_status = lambda: None

            with contextlib.redirect_stdout(io.StringIO()):
                store.login_api_profile(
                    name="peach-api",
                    api_key="sk-test-placeholder",
                    provider="PeachCode",
                    base_url="https://cli.rhinelab.com.cn",
                    model="gpt-5.5",
                    review_model="gpt-5.5",
                    reasoning_effort="xhigh",
                    wire_api="responses",
                    requires_openai_auth=True,
                    disable_response_storage=True,
                    network_access="enabled",
                    context_window=1000000,
                    compact_token_limit=900000,
                    replace=False,
                )

            active_auth = json.loads(store.auth_file.read_text())
            saved_auth = json.loads(store.profile_path("peach-api").read_text())
            config = store.config_file.read_text()

            self.assertEqual(active_auth["auth_mode"], "apikey")
            self.assertEqual(saved_auth["OPENAI_API_KEY"], "sk-test-placeholder")
            self.assertEqual(store.active_name(), "peach-api")
            self.assertIn('model_provider = "PeachCode"', config)
            self.assertIn("[model_providers.PeachCode]", config)
            self.assertIn('base_url = "https://cli.rhinelab.com.cn"', config)
            self.assertEqual(store.profile_config_path("peach-api").read_text(), config)

    def test_login_api_profile_requires_replace_for_existing_profile(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            _write_json(store.profile_path("peach-api"), _api_key_auth())
            with self.assertRaisesRegex(RuntimeError, "profile already exists"):
                store.login_api_profile(
                    name="peach-api",
                    api_key="sk-test-placeholder",
                    provider="PeachCode",
                    base_url="https://cli.rhinelab.com.cn",
                    model="gpt-5.5",
                    review_model="gpt-5.5",
                    reasoning_effort="xhigh",
                    wire_api="responses",
                    requires_openai_auth=True,
                    disable_response_storage=True,
                    network_access="enabled",
                    context_window=1000000,
                    compact_token_limit=900000,
                    replace=False,
                    restart_app_server=False,
                )

    def test_restart_codex_app_server_stops_cached_processes(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            kill_calls = []
            popen_calls = []

            def fake_popen(argv, **_kwargs):
                popen_calls.append(argv)

                class Process:
                    def poll(self):
                        return None

                return Process()

            def fake_kill(pid, sig):
                kill_calls.append((pid, sig))

            with patch.object(store, "codex_app_server_pids", return_value=[11, 22]):
                with patch.object(store, "_kill_pid", fake_kill):
                    with patch.object(store, "_pid_exists", return_value=False):
                        with patch("codex_auth.store.time.sleep", lambda _seconds: None):
                            with patch("codex_auth.store.shutil.which", return_value="/bin/codex"):
                                with patch("codex_auth.store.subprocess.Popen", fake_popen):
                                    with contextlib.redirect_stdout(io.StringIO()):
                                        store.restart_codex_app_server()

            self.assertEqual(kill_calls, [(11, signal.SIGTERM), (22, signal.SIGTERM)])
            self.assertEqual(popen_calls, [["/bin/codex", "app-server", "--listen", "unix://"]])

    def test_codex_app_server_matcher_ignores_shell_commands(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            self.assertTrue(
                store._is_codex_app_server_argv(["/usr/bin/codex", "app-server", "--listen", "unix://"])
            )
            self.assertTrue(store._is_codex_app_server_argv(["codex", "app-server", "proxy"]))
            self.assertFalse(
                store._is_codex_app_server_argv(
                    ["zsh", "-c", 'pgrep -af "codex app-server --listen unix://"']
                )
            )
            self.assertFalse(
                store._is_codex_app_server_argv(
                    ["/bin/sh", "-c", "PATH=$HOME/.local/bin:$PATH; codex app-server proxy"]
                )
            )

    def test_restart_codex_app_server_without_codex_only_stops_cached_processes(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            kill_calls = []

            def fake_kill(pid, sig):
                kill_calls.append((pid, sig))

            with patch.object(store, "codex_app_server_pids", return_value=[11, 22]):
                with patch.object(store, "_kill_pid", fake_kill):
                    with patch.object(store, "_pid_exists", return_value=False):
                        with patch("codex_auth.store.time.sleep", lambda _seconds: None):
                            with patch("codex_auth.store.shutil.which", return_value=None):
                                with contextlib.redirect_stderr(io.StringIO()):
                                    store.restart_codex_app_server()

            self.assertEqual(kill_calls, [(11, signal.SIGTERM), (22, signal.SIGTERM)])

    def test_stop_codex_app_server_processes_escalates_remaining_pids(self):
        with tempfile.TemporaryDirectory() as codex_home:
            store = self._store(codex_home)
            kill_calls = []

            def fake_kill(pid, sig):
                kill_calls.append((pid, sig))

            with patch.object(store, "codex_app_server_pids", return_value=[11]):
                with patch.object(store, "_kill_pid", fake_kill):
                    with patch.object(store, "_pid_exists", return_value=True):
                        with patch("codex_auth.store.time.sleep", lambda _seconds: None):
                            with patch("codex_auth.store.time.time", side_effect=[0, 3]):
                                self.assertEqual(store.stop_codex_app_server_processes(), [11])

            self.assertEqual(kill_calls, [(11, signal.SIGTERM), (11, signal.SIGKILL)])

if __name__ == "__main__":
    unittest.main()
