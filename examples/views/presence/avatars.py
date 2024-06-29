import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Avatar:
    name: str
    color: str

    @classmethod
    def generate(cls):
        return cls(_generate_avatar_name(), _generate_saturated_color())


class UserRepository:
    _all_users: list[Avatar]

    def __init__(self):
        self._all_users = []

    def register_avatar(self) -> Avatar:
        avatar = Avatar.generate()
        self._all_users.append(avatar)
        return avatar

    def unregister_avatar(self, avatar: Optional[Avatar]):
        if avatar:
            self._all_users.remove(avatar)

    def all(self) -> list[Avatar]:
        return self._all_users


def _generate_avatar_name():
    adjectives = [
        "Amazing",
        "Brave",
        "Cheerful",
        "Daring",
        "Energetic",
        "Friendly",
        "Gentle",
        "Happy",
        "Incredible",
        "Jolly",
        "Kind",
        "Lively",
        "Mighty",
        "Noble",
        "Optimistic",
        "Playful",
        "Quirky",
        "Radiant",
        "Sleepy",
        "Terrific",
        "Unique",
        "Vibrant",
        "Witty",
        "Xenial",
        "Youthful",
        "Zealous",
    ]

    animals = [
        "Aardvark",
        "Bear",
        "Cat",
        "Dog",
        "Elephant",
        "Flamingo",
        "Giraffe",
        "Hippo",
        "Iguana",
        "Jaguar",
        "Kangaroo",
        "Lion",
        "Monkey",
        "Narwhal",
        "Octopus",
        "Penguin",
        "Quokka",
        "Rabbit",
        "Sloth",
        "Tiger",
        "Unicorn",
        "Vulture",
        "Walrus",
        "Xerus",
        "Yak",
        "Zebra",
    ]

    adjective = random.choice(adjectives)
    animal = random.choice(animals)

    return f"{adjective} {animal}"


def _generate_saturated_color():
    saturated_palette = [
        "#FF6F61",
        "#FFB347",
        "#50BFE6",
        "#76D7C4",
        "#F39C12",
        "#D4AC0D",
        "#A569BD",
        "#58D68D",
        "#5DADE2",
        "#DC7633",
        "#C0392B",
        "#16A085",
        "#8E44AD",
        "#F1C40F",
        "#E74C3C",
        "#3498DB",
        "#27AE60",
        "#D35400",
        "#9B59B6",
        "#1ABC9C",
    ]

    return random.choice(saturated_palette)
