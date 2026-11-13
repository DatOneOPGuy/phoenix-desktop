"""The ClamAV postinstall status file is read out of world-writable /tmp.

Its name carries a uuid, so the path is unpredictable — but that is the only
thing stopping a local process from planting something there, so the reader
verifies what it actually opened rather than trusting the path.
"""

import json
import os

import pytest

pytestmark = [pytest.mark.security,
              pytest.mark.skipif(os.name == "nt", reason="POSIX modes only")]


@pytest.fixture()
def read_status():
    from plugins.antivirus.clamav_platform_darwin import _read_trusted_status
    return _read_trusted_status


def _write(path, content='{"status": "success"}', mode=0o600):
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    return str(path)


def test_well_formed_file_is_read(read_status, tmp_path):
    p = _write(tmp_path / "ok.status")
    assert read_status(p) == {"status": "success"}


def test_symlink_is_refused(read_status, tmp_path):
    """O_NOFOLLOW: a symlink dropped in our place must not be followed."""
    target = _write(tmp_path / "target.status")
    link = tmp_path / "link.status"
    os.symlink(target, link)
    assert read_status(str(link)) is None


def test_fifo_does_not_block_and_is_refused(read_status, tmp_path):
    """A fifo must be rejected, not block the caller.

    Opening a fifo read-only blocks until a writer appears, so without
    O_NONBLOCK a planted fifo would hang the install poller indefinitely —
    the check has to survive the open, not just follow it.
    """
    import signal

    fifo = tmp_path / "fifo.status"
    os.mkfifo(fifo)

    def _timeout(_sig, _frm):
        raise AssertionError("reading a fifo blocked — O_NONBLOCK is missing")

    old = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(10)
    try:
        assert read_status(str(fifo)) is None
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_group_or_world_writable_is_refused(read_status, tmp_path):
    p = _write(tmp_path / "ww.status", mode=0o666)
    assert read_status(p) is None


def test_malformed_json_is_refused(read_status, tmp_path):
    p = _write(tmp_path / "bad.status", "{not json")
    assert read_status(p) is None


def test_missing_file_is_refused(read_status, tmp_path):
    assert read_status(str(tmp_path / "nope.status")) is None


def test_poll_treats_untrusted_file_as_unfinished(tmp_path):
    """Fail closed: an untrusted file must read as "keep waiting", never success."""
    from plugins.antivirus import clamav_platform_darwin as mod

    p = _write(tmp_path / "ww.status", json.dumps({"status": "success"}), mode=0o666)
    finished, success, details = mod._poll_setup_status(p)
    assert (finished, success, details) == (False, False, {})
