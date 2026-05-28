import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auth.cli import main
from codex_auth.store import AuthStore


class CliTests(unittest.TestCase):
    def test_login_api_is_interactive_only(self):
        with tempfile.TemporaryDirectory() as codex_home:
            with patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    self.assertEqual(main(["login-api", "peach-api"]), 1)
            self.assertIn("login-api expects 0 argument", stderr.getvalue())

    def test_login_api_interactive_creates_api_profile(self):
        with tempfile.TemporaryDirectory() as codex_home:
            inputs = iter(["peach-api", "", "", "", "n"])

            with patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                with patch("builtins.input", lambda _prompt: next(inputs)):
                    with patch("codex_auth.cli.getpass.getpass", return_value="sk-test-placeholder"):
                        with patch.object(AuthStore, "restart_codex_app_server", lambda _self: None):
                            with patch.object(AuthStore, "codex_login_status", lambda _self: None):
                                with contextlib.redirect_stdout(io.StringIO()):
                                    self.assertEqual(main(["login-api"]), 0)

            home = Path(codex_home)
            auth = json.loads((home / "auth.json").read_text())
            config = (home / "config.toml").read_text()
            saved_auth = json.loads(
                (home / "auth-profiles" / "peach-api.json").read_text()
            )

            self.assertEqual(auth["auth_mode"], "apikey")
            self.assertEqual(saved_auth["OPENAI_API_KEY"], "sk-test-placeholder")
            self.assertIn('model_provider = "PeachCode"', config)
            self.assertIn('base_url = "https://cli.rhinelab.com.cn"', config)
            self.assertEqual(
                (home / "auth-profiles" / ".active").read_text().strip(),
                "peach-api",
            )


if __name__ == "__main__":
    unittest.main()
