"""Chat E2EE must use vodozemac, never libolm.

libolm is deprecated and unmaintained upstream; matrix-nio prefers vodozemac
but will fall back to python-olm when it is importable. A build that happened
to carry python-olm would silently run user chat on the deprecated backend, so
this pins the property rather than trusting the lockfile.
"""

import importlib.util

import pytest


@pytest.mark.security
def test_vodozemac_is_available():
    """The supported Megolm backend must be installed."""
    assert importlib.util.find_spec("vodozemac") is not None, (
        "vodozemac is missing — matrix-nio would fall back to libolm or fail"
    )


@pytest.mark.security
def test_libolm_is_not_installed():
    """python-olm must not be importable, so no fallback can be selected."""
    spec = importlib.util.find_spec("olm")
    assert spec is None, (
        f"python-olm (libolm) is installed at {spec.origin!r}. Chat E2EE must "
        "run on vodozemac; remove python-olm from the environment and from any "
        "frozen build."
    )
