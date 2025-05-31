from dataclasses import dataclass
from typing import Any


@dataclass
class InfoEvent:
    name: str
    payload: Any = None
