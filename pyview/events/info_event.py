from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass
class InfoEvent:
    name: str
    payload: Any = None


class InfoEventScheduler(Protocol):
    def schedule_info(self, event: InfoEvent, seconds: float):
        pass

    def schedule_info_once(self, event: InfoEvent, seconds: Optional[float] = None):
        pass
