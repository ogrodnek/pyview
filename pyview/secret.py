import os
import secrets

_SECRET = None


def get_secret() -> str:
    """
    Get the secret key from the environment, or generate a new one.
    """
    global _SECRET
    if _SECRET is None:
        secret = os.environ.get("PYVIEW_SECRET")
        if secret is None:
            secret = secrets.token_urlsafe(16)
        _SECRET = secret

    return _SECRET
