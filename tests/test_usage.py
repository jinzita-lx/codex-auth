import json
import tempfile
import unittest
from pathlib import Path

from codex_auth.usage import api_provider_name, fetch_usage


class UsageTests(unittest.TestCase):
    def test_api_profile_with_config_reports_provider_without_network_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "peach-api.json"
            profile.write_text(
                json.dumps(
                    {
                        "auth_mode": "apikey",
                        "OPENAI_API_KEY": "sk-test-placeholder",
                    }
                ),
                encoding="utf-8",
            )
            profile.with_name("peach-api.config.toml").write_text(
                'model_provider = "PeachCode"\n'
                'model = "gpt-5.5"\n'
                '[model_providers.PeachCode]\n'
                'base_url = "https://cli.rhinelab.com.cn"\n',
                encoding="utf-8",
            )

            summary = fetch_usage(profile)

            self.assertEqual(api_provider_name(profile), "PeachCode")
            self.assertEqual(summary.status, "ok")
            self.assertEqual(summary.plan, "PeachCode")

    def test_api_provider_name_falls_back_to_provider_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "custom.json"
            profile.write_text("{}", encoding="utf-8")
            profile.with_name("custom.config.toml").write_text(
                '[model_providers."Provider With Space"]\n',
                encoding="utf-8",
            )

            self.assertEqual(api_provider_name(profile), "Provider With Space")


if __name__ == "__main__":
    unittest.main()
