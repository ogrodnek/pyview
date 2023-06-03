from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from typing import Optional
import hmac
from pyview.secret import get_secret


def generate_csrf_token(value: str, salt: Optional[str] = None) -> str:
    """
    Generate a CSRF token.
    """
    s = URLSafeTimedSerializer(get_secret(), salt=salt or "pyview-csrf-token")
    return s.dumps(value)  # type: ignore


def validate_csrf_token(data: str, expected: str, salt: Optional[str] = None) -> bool:
    """
    Validate a CSRF token.
    """
    s = URLSafeTimedSerializer(get_secret(), salt=salt or "pyview-csrf-token")
    try:
        token = s.loads(data, max_age=3600)
        return hmac.compare_digest(token, expected)
    except (BadData, SignatureExpired) as e:
        print(e)
        return False
