"""
Unit tests for Linux Wazuh agent install-dir detection.

Covers plugins/wazuh/agent/wazuh_functions_linux.py:
- installed_agent_dir: candidate search order
- is_app_managed_agent: only /var/ossec is the app's own install

os.path.isdir is mocked — safe to run anywhere.
"""
from unittest.mock import patch

import pytest

from plugins.wazuh.agent import wazuh_functions_linux as linux


def _only_dirs(*present):
    return patch(
        "plugins.wazuh.agent.wazuh_functions_linux.os.path.isdir",
        side_effect=lambda path: path in present,
    )


@pytest.mark.unit
class TestInstalledAgentDir:
    def test_candidates(self):
        assert linux.LINUX_WAZUH_DIR_CANDIDATES == (
            "/var/ossec", "/opt/resistine", "/opt/phoenix-agent", "/opt/agent-phoenix")

    @pytest.mark.parametrize("path", linux.LINUX_WAZUH_DIR_CANDIDATES)
    def test_each_location_is_found(self, path):
        with _only_dirs(path):
            assert linux.installed_agent_dir() == path
            assert linux.is_agent_installed() is True

    def test_first_match_wins(self):
        with _only_dirs("/opt/resistine", "/opt/agent-phoenix"):
            assert linux.installed_agent_dir() == "/opt/resistine"

    def test_nothing_installed(self):
        with _only_dirs():
            assert linux.installed_agent_dir() is None
            assert linux.is_agent_installed() is False

    @pytest.mark.parametrize(
        "path", ["/opt/resistine", "/opt/phoenix-agent", "/opt/agent-phoenix"])
    def test_other_locations_are_not_app_managed(self, path):
        with _only_dirs(path):
            assert linux.is_app_managed_agent() is False
