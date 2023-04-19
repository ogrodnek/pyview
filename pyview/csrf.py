from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
import secrets
from typing import Optional
import hmac
import os


def generate_csrf_token(value: str, salt: Optional[str] = None) -> str:
    """
    Generate a CSRF token.
    """
    s = URLSafeTimedSerializer(_get_secret(), salt=salt or "pyview-csrf-token")
    return s.dumps(value)  # type: ignore


def validate_csrf_token(data: str, expected: str, salt: Optional[str] = None) -> bool:
    """
    Validate a CSRF token.
    """
    s = URLSafeTimedSerializer(_get_secret(), salt=salt or "pyview-csrf-token")
    try:
        token = s.loads(data, max_age=3600)
        return hmac.compare_digest(token, expected)
    except (BadData, SignatureExpired) as e:
        print(e)
        return False


_SECRET = None


def _get_secret() -> str:
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
