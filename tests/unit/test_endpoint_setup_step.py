"""The Windows/Linux endpoint step stays incomplete until its install worker
returns: the agent package starts the service before the root script has
written the enrollment key, and the wizard used to finish on that
(plugins/login/setup_steps.py)."""

import threading

import pytest

from plugins.login import setup_steps


@pytest.mark.unit
def test_not_complete_while_install_runs(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(setup_steps, "_wazuh_installed", lambda: True)
    monkeypatch.setattr(setup_steps, "_wazuh_running", lambda: True)
    monkeypatch.setattr(setup_steps, "_wazuh_connection", lambda: "connected")
    monkeypatch.setattr(setup_steps, "_wazuh_activate",
                        lambda *_a: release.wait(5) or True)
    monkeypatch.setattr(setup_steps, "_maybe_forward_clamav", lambda _s: None)

    step = setup_steps._EndpointStepDirect(app=None)
    assert step.is_complete()  # already set up before the wizard ran
    done = threading.Event()
    monkeypatch.setattr(step, "_run_bg",
                        lambda fn: threading.Thread(target=lambda: (fn(), done.set())).start())
    step.begin(lambda _m: None)
    assert not step.is_complete()
    release.set()
    assert done.wait(5)
    assert step.is_complete()
