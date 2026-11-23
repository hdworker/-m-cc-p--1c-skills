"""Environment-only credentials for 1C infobase connections.

Infobase authentication is always sourced from ONEC_USER and ONEC_PWD.
Project/store registry fields and CLI credential values are never fallbacks.
"""

import os


class OnecCredentialsError(ValueError):
    """Raised when required infobase credentials are not configured."""


def require_onec_credentials(environ=None):
    """Return (username, password) from ONEC_* variables only.

    ONEC_USER must be non-empty. ONEC_PWD must be present, but may be empty for
    an account with no password. Empty and missing are deliberately distinct.
    """
    source = os.environ if environ is None else environ
    username = source.get("ONEC_USER")
    password = source.get("ONEC_PWD")
    missing = []
    if not username:
        missing.append("ONEC_USER")
    if password is None:
        missing.append("ONEC_PWD")
    if missing:
        raise OnecCredentialsError(
            "Задайте переменные среды для подключения к инфобазе: " + ", ".join(missing)
        )
    return username, password


def apply_onec_credentials(args, environ=None):
    """Overwrite CLI namespace credentials with the required environment values."""
    username, password = require_onec_credentials(environ)
    args.UserName = username
    args.Password = password
    return username, password
