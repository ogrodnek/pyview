from dataclasses import dataclass, field
import uuid
from typing import Optional


@dataclass
class Attribution:
    name: str
    url: str


@dataclass
class Recipe:
    name: str
    img: str
    time: str

    attribution: Attribution

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    rating: Optional[int] = None
    bookmarked: bool = False


def all_recipes() -> list[Recipe]:
    return [
        Recipe(
            name="Donuts",
            img="/static/brooke-lark-V4MBq8kue3U-unsplash.jpg",
            time="90 mins",
            attribution=Attribution(
                "Brooke Lark",
                "https://unsplash.com/@brookelark?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
        Recipe(
            name="Chickpea Salad",
            img="/static/deryn-macey-B-DrrO3tSbo-unsplash.jpg",
            time="30 mins",
            attribution=Attribution(
                "Deryn Macey",
                "https://unsplash.com/@derynmacey?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
        Recipe(
            name="Chia Pudding",
            img="/static/maryam-sicard-Tz1sAv3xnt0-unsplash.jpg",
            time="20 mins",
            attribution=Attribution(
                "Maryam Sicard",
                "https://unsplash.com/@maryamsicard?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
        Recipe(
            name="Cinnamon Rolls",
            img="/static/nick-bratanek-RBwli5VzJXo-unsplash.jpg",
            time="45 mins",
            attribution=Attribution(
                "Nick Bratanek",
                "https://unsplash.com/@nickbratanek?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
        Recipe(
            name="Watermelon Salad",
            img="/static/taylor-kiser-EvoIiaIVRzU-unsplash.jpg",
            time="15 mins",
            attribution=Attribution(
                "Taylor Kiser",
                "https://unsplash.com/@foodfaithfit?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
        Recipe(
            name="Curry",
            img="static/taylor-kiser-POFG828-GQc-unsplash.jpg",
            time="30 mins",
            attribution=Attribution(
                "Taylor Kiser",
                "https://unsplash.com/@foodfaithfit?utm_content=creditCopyText&utm_medium=referral&utm_source=unsplash",
            ),
        ),
    ]
