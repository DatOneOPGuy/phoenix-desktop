"""
Unit tests for plugins/wazuh/agent/enrollment.py and its use by the installers.

- request(): POST /v1/agent/enroll through the provisioning client; the key
  line must match the answer's agent; any failure -> None (agent-auth fallback)
- the private key file: 0600 in a fresh 0700 directory, removed by discard()
- Linux / Windows install scripts write the API key instead of running
  agent-auth, and fall back to agent-auth without it

The HTTP client and the privileged runners are mocked.
"""
import base64
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from plugins.wazuh.agent import enrollment

LINE = "012 laptop-1a2b any " + "ab" * 32


def _resp(status=200, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    return r


def _answer(line=LINE, agent_id="012", name="laptop-1a2b"):
    return {"agent_id": agent_id, "agent_name": name, "group": "u_alice",
            "manager": "dashboard.phoenix.exposed:1517",
            "key": base64.b64encode(line.encode()).decode()}


@pytest.fixture
def api():
    with patch("plugins.vpn.provisioning._authorized_request") as req:
        yield req


@pytest.mark.unit
@pytest.mark.security
class TestRequest:
    def test_success(self, api):
        api.return_value = _resp(200, _answer())
        e = enrollment.request("laptop-1a2b")
        try:
            assert (e.agent_id, e.agent_name, e.group, e.key_line) == \
                ("012", "laptop-1a2b", "u_alice", LINE)
            assert api.call_args.args == ("POST", "/v1/agent/enroll")
            assert api.call_args.kwargs["json"] == {"name": "laptop-1a2b"}
            with open(e.key_file) as f:
                assert f.read() == LINE + "\n"
            assert stat.S_IMODE(os.stat(e.key_file).st_mode) == 0o600
            assert stat.S_IMODE(os.stat(os.path.dirname(e.key_file)).st_mode) == 0o700
        finally:
            enrollment.discard(e)
        assert not os.path.exists(os.path.dirname(e.key_file))

    def test_server_keeps_earlier_name(self, api):
        line = "007 old-name any " + "cd" * 32
        api.return_value = _resp(200, _answer(line, "007", "old-name"))
        e = enrollment.request("laptop-1a2b-123456")
        enrollment.discard(e)
        assert e.agent_name == "old-name"

    @pytest.mark.parametrize("body", [
        _answer(agent_id="013"),                                   # key for another id
        _answer(name="other"),                                     # key for another name
        _answer(line="012 laptop-1a2b any short"),                 # not a key
        _answer(line=LINE + "\n013 x any " + "ab" * 32),           # two lines
        {**_answer(), "key": "%%%"},                               # not base64
        {"detail": "x"},                                           # wrong shape
    ])
    def test_bad_answers(self, api, body):
        api.return_value = _resp(200, body)
        assert enrollment.request("laptop-1a2b") is None

    @pytest.mark.parametrize("status", [401, 409, 422, 503])
    def test_http_errors_fall_back(self, api, status):
        api.return_value = _resp(status, {"detail": "nope"})
        assert enrollment.request("laptop-1a2b") is None

    def test_not_signed_in_falls_back(self, api):
        from plugins.vpn.provisioning import ProvisioningError
        api.side_effect = ProvisioningError("You're not signed in to Phoenix.")
        assert enrollment.request("laptop-1a2b") is None

    @pytest.mark.parametrize("name", ["", "a b", "x" * 65, "a;b"])
    def test_bad_name_no_call(self, api, name):
        assert enrollment.request(name) is None
        api.assert_not_called()


def _enrolled(tmp_path):
    key_file = tmp_path / "client.keys"
    key_file.write_text(LINE + "\n")
    return enrollment.Enrollment("012", "laptop-1a2b", "u_alice", LINE, str(key_file))


@pytest.mark.unit
class TestLinuxInstall:
    def _script(self, enrolled):
        from plugins.wazuh.agent import wazuh_functions_linux as wl
        with patch.object(wl, "download_package", return_value="/tmp/p.deb"), \
                patch.object(wl, "_get_os_info", return_value="deb"), \
                patch.object(wl, "get_agent_name", return_value="host-uuid"), \
                patch.object(wl, "get_agent_group", return_value="grp"), \
                patch.object(wl.enrollment, "request", return_value=enrolled), \
                patch.object(wl.enrollment, "discard") as discard, \
                patch.object(wl, "is_agent_installed", return_value=True), \
                patch.object(wl, "run_privileged_command", return_value=(True, "")) as run:
            assert wl.full_install() is True
        discard.assert_called_once_with(enrolled)
        return run.call_args.args[0][2]

    def test_api_key_replaces_agent_auth(self, tmp_path):
        e = _enrolled(tmp_path)
        script = self._script(e)
        assert "agent-auth" not in script
        assert e.key_file in script and enrollment.KEY_LINE_PATTERN in script
        assert "WAZUH_AGENT_NAME='laptop-1a2b'" in script  # the server's name
        assert LINE not in script  # the key itself never goes on a command line

    def test_fallback_agent_auth(self):
        script = self._script(None)
        assert "/bin/agent-auth' -m 'dashboard.phoenix.exposed' -p '1515'" in script
        assert "-A 'host-uuid' -G 'grp'" in script


@pytest.mark.unit
class TestWindowsInstall:
    def test_api_key_replaces_agent_auth(self, tmp_path):
        from plugins.wazuh.agent import wazuh_functions_windows as ww
        e = _enrolled(tmp_path)
        script = ww._build_install_script(None, r"C:\t\p.msi", "laptop-1a2b", "grp", r"C:\b", e)
        assert "agent-auth.exe" not in script
        assert e.key_file in script and enrollment.KEY_LINE_PATTERN in script
        assert LINE not in script
        assert "WAZUH_MANAGER_PORT=1517" in script

    def test_fallback_agent_auth(self):
        from plugins.wazuh.agent import wazuh_functions_windows as ww
        script = ww._build_install_script(None, r"C:\t\p.msi", "host", "grp", r"C:\b")
        assert "agent-auth.exe" in script
        assert "-G 'grp'" in script
