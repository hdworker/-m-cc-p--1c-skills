#!/usr/bin/env python3
"""Unit tests for the shared ONEC_* infobase credential policy."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SHARED = Path(__file__).resolve().parents[2] / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))

from onec_credentials import (  # noqa: E402
    OnecCredentialsError,
    apply_onec_credentials,
    require_onec_credentials,
)

INIT_SCRIPT = Path(__file__).resolve().parents[2] / ".dsh" / "skills" / "1c-init" / "scripts" / "1c-init.py"
_INIT_SPEC = importlib.util.spec_from_file_location("onec_init", INIT_SCRIPT)
_onec_init = importlib.util.module_from_spec(_INIT_SPEC)
_INIT_SPEC.loader.exec_module(_onec_init)


class OnecCredentialsTests(unittest.TestCase):
    def test_reads_both_values_from_environment(self):
        self.assertEqual(
            require_onec_credentials({"ONEC_USER": "env-user", "ONEC_PWD": "env-pwd"}),
            ("env-user", "env-pwd"),
        )

    def test_empty_password_is_explicit_and_allowed(self):
        self.assertEqual(
            require_onec_credentials({"ONEC_USER": "env-user", "ONEC_PWD": ""}),
            ("env-user", ""),
        )

    def test_missing_or_empty_username_fails_without_disclosing_secrets(self):
        for environ in (
            {"ONEC_PWD": "secret-sentinel"},
            {"ONEC_USER": "env-user"},
            {"ONEC_USER": "", "ONEC_PWD": "secret-sentinel"},
        ):
            with self.subTest(environ=environ):
                with self.assertRaises(OnecCredentialsError) as error:
                    require_onec_credentials(environ)
                self.assertNotIn("secret-sentinel", str(error.exception))

    def test_environment_overrides_cli_or_registry_values(self):
        args = SimpleNamespace(UserName="registry-user", Password="registry-pwd")
        result = apply_onec_credentials(
            args, {"ONEC_USER": "env-user", "ONEC_PWD": "env-pwd"}
        )
        self.assertEqual(result, ("env-user", "env-pwd"))
        self.assertEqual((args.UserName, args.Password), ("env-user", "env-pwd"))

    def test_project_init_removes_legacy_infobase_credentials_only(self):
        record = {
            "id": "dev",
            "user": "legacy-user",
            "password": "legacy-password",
            "repository": {"user": "repo-user", "password": "repo-password"},
        }
        self.assertEqual(
            _onec_init.without_infobase_credentials(record),
            {
                "id": "dev",
                "repository": {"user": "repo-user", "password": "repo-password"},
            },
        )
        self.assertIn("user", record)
        self.assertIn("password", record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
