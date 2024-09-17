from pydantic import BaseModel, Field

import datetime
import uuid
import random


class Plant(BaseModel):
    name: str = Field(min_length=3, max_length=20)
    watering_schedule_days: int = Field(ge=1, le=30)
    last_watered: datetime.datetime = Field(default_factory=datetime.datetime.now)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def needs_watering(self) -> bool:
        return (
            datetime.datetime.now() - self.last_watered
        ).days >= self.watering_schedule_days


PLANTS = None


def plants(reset: bool = False) -> list[Plant]:
    global PLANTS
    if not PLANTS or reset:
        PLANTS = _plants()
    return PLANTS


def _plants() -> list[Plant]:
    return [
        Plant(name="Aloe", watering_schedule_days=7, last_watered=_random_date()),
        Plant(name="Cactus", watering_schedule_days=14, last_watered=_random_date()),
        Plant(name="Fern", watering_schedule_days=7, last_watered=_random_date()),
        Plant(
            name="Snake Plant", watering_schedule_days=14, last_watered=_random_date()
        ),
        Plant(
            name="Spider Plant", watering_schedule_days=7, last_watered=_random_date()
        ),
        Plant(name="Succulent", watering_schedule_days=14, last_watered=_random_date()),
    ]


def _random_date() -> datetime.datetime:
    return datetime.datetime.now() - datetime.timedelta(
        days=random.randint(1, 15),
        hours=random.randint(1, 23),
        minutes=random.randint(1, 59),
    )
