from dataclasses import dataclass
from typing import Any, Union


@dataclass
class InfoEventWithPayload:
    event: str
    payload: Any


InfoEvent = Union[InfoEventWithPayload, str]
