from typing import Any, cast
from itsdangerous import URLSafeSerializer
from pyview.secret import get_secret


def serialize_session(session: dict[str, Any]) -> str:
    s = URLSafeSerializer(get_secret(), salt="pyview-session")
    return cast(str, s.dumps(session))


def deserialize_session(ser: str) -> dict[str, Any]:
    s = URLSafeSerializer(get_secret(), salt="pyview-session")
    return cast(dict[str, Any], s.loads(ser))
