"""Minimal environment whitelist for EDA subprocesses.

Prevents DATABASE_URL, SECRET_KEY, and other sensitive variables from
leaking into ngspice, Magic, Netgen, or KLayout child processes.
"""

from __future__ import annotations

import os

# Only these variables are forwarded from the host environment.
# All EDA-specific overrides (HOME, PDK_ROOT, PDK) are set at call-site.
_ALLOWED_KEYS = frozenset({
    "PATH",
    "LANG",
    "LC_ALL",
    "TERM",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "USER",
    "LOGNAME",
    "DISPLAY",
    "XDG_RUNTIME_DIR",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
})


def safe_env(**overrides: str) -> dict[str, str]:
    """Return a sanitised environment dict for ``subprocess.run()``.

    Only whitelisted keys from ``os.environ`` are forwarded, plus any
    explicit *overrides*.  This prevents credentials such as
    ``DATABASE_URL`` and ``SECRET_KEY`` from reaching EDA tools.
    """
    env = {key: os.environ[key] for key in _ALLOWED_KEYS if key in os.environ}
    env.update(overrides)
    return env
