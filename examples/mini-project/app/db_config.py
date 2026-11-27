"""Reference implementation of the shop.api -> shop.db TLS requirement.

Fixture only. It exists so the config-only constraint `db-connection-tls` has an
executable check; nothing in the LikeC4 model, the manifests or a deployment
imports it.
"""
from __future__ import annotations

from typing import Final
from urllib.parse import parse_qsl, urlparse

#: The weakest mode this application accepts. `require` encrypts the connection
#: but does not verify the server certificate chain; see the change record's
#: open question about `verify-full`.
REQUIRED_SSLMODE: Final = "require"
ALLOWED_SSLMODES: Final = ("require", "verify-ca", "verify-full")
#: Modes that leave the connection in plaintext or permit a plaintext fallback.
PLAINTEXT_FALLBACK_MODES: Final = ("disable", "allow", "prefer")


class InsecureConfiguration(ValueError):
    """Raised when a connection string could fall back to plaintext."""


def build_dsn(*, host: str, database: str, user: str, sslmode: str = REQUIRED_SSLMODE) -> str:
    """Return a DSN that pins TLS, refusing plaintext-capable modes."""
    if sslmode in PLAINTEXT_FALLBACK_MODES:
        raise InsecureConfiguration(f"sslmode={sslmode} permits plaintext")
    if sslmode not in ALLOWED_SSLMODES:
        raise ValueError(f"unsupported sslmode: {sslmode}")
    return f"postgresql://{user}@{host}/{database}?sslmode={sslmode}"


def assert_tls(dsn: str) -> str:
    """Verify a DSN pins TLS; return the sslmode. Raises InsecureConfiguration."""
    parsed = urlparse(dsn)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise InsecureConfiguration("Expected a PostgreSQL connection URL")
    # libpq connection-parameter precedence must not make an earlier safe value
    # conceal a later unsafe one (sslmode=require&sslmode=disable).
    modes = [value for name, value in parse_qsl(parsed.query, keep_blank_values=True)
             if name == "sslmode"]
    if len(modes) != 1:
        raise InsecureConfiguration("DSN must pin exactly one sslmode")
    mode = modes[0]
    if mode in PLAINTEXT_FALLBACK_MODES:
        raise InsecureConfiguration(f"sslmode={mode} permits plaintext")
    if mode not in ALLOWED_SSLMODES:
        raise ValueError(f"unsupported sslmode: {mode}")
    return mode
