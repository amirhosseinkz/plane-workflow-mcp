from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import configuration


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class ConfigurationTests(unittest.TestCase):
    def test_stores_only_non_secret_values_in_settings_file(self) -> None:
        keyring = _Keyring()
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"PLANE_WORKFLOW_HOME": directory}, clear=False), patch.object(configuration, "keyring", keyring):
            path = configuration.save_stored_plane_settings(
                base_url="https://plane.example.test/",
                workspace="workspace",
                api_key="secret-value",
            )
            loaded = configuration.load_stored_plane_settings()

            self.assertEqual(loaded, configuration.StoredPlaneSettings("https://plane.example.test", "secret-value", "workspace", "default"))
            self.assertNotIn("secret-value", path.read_text(encoding="utf-8"))
            self.assertEqual(keyring.values[(configuration.KEYRING_SERVICE, "default")], "secret-value")

    def test_returns_none_before_first_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"PLANE_WORKFLOW_HOME": directory}, clear=False):
            self.assertIsNone(configuration.load_stored_plane_settings())

    def test_removal_deletes_both_profile_and_secret(self) -> None:
        keyring = _Keyring()
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"PLANE_WORKFLOW_HOME": directory}, clear=False), patch.object(configuration, "keyring", keyring):
            configuration.save_stored_plane_settings(base_url="https://plane.example.test", workspace="workspace", api_key="secret")
            self.assertTrue(configuration.remove_stored_plane_settings())
            self.assertIsNone(configuration.load_stored_plane_settings())
            self.assertEqual(keyring.values, {})
