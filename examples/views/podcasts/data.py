from dataclasses import dataclass


@dataclass
class Episode:
    id: int
    title: str
    published: str


@dataclass
class Podcast:
    id: int
    title: str
    coverUrl: str

    description: str

    episodes: list[Episode]


def podcasts() -> list[Podcast]:
    return [
        Podcast(
            1,
            "Python Bytes",
            "https://pythonbytes.fm/static/img/podcast-theme-img_1400.png",
            "Developer headlines delivered directly to your earbuds",
            [
                Episode(323, "#323: AI search wars have begun", "Tue, Feb 14, 2023"),
                Episode(
                    322,
                    "#322: Python Packages, Let Me Count The Ways",
                    "Tue, 07 Feb 2023",
                ),
                Episode(321, "#321: A Memorial To Apps Past", "Mon, 30 Jan 2023 "),
            ],
        ),
        Podcast(
            2,
            "Accidental Tech Podcast",
            "https://cdn.atp.fm/artwork",
            "Three nerds discussing tech, Apple, programming, and loosely related matters.",
            [
                Episode(
                    522, "522: I’ll Just Keep You for Ten Years", "Thu, 16 Feb 2023"
                ),
                Episode(521, "521: Dance Compatible", "Thu, 09 Feb 2023"),
                Episode(520, "520: Bananas Ingestion System", "Thu, 02 Feb 2023"),
            ],
        ),
        Podcast(
            3,
            "Stay Tuned with Preet",
            "https://cafe.imgix.net/wp-content/uploads/2020/07/stay-tuned-square.jpg?q=65&w=600&ar=1:1&fit=crop",
            "Join former U.S. Attorney Preet Bharara as he breaks down legal topics in the news and engages thought leaders in a podcast about power, policy, and justice.",
            [
                Episode(
                    1,
                    "What’s Up With the UFOs? (with Michael Morell)",
                    "Thurs, February 16, 2023",
                ),
                Episode(
                    2,
                    "Salman Rushdie's Defiance (with David Remnick)",
                    "Thu, February 9, 2023",
                ),
                Episode(3, "Above the Law? (with Elie Honig)", "Thu, February 2, 2023"),
            ],
        ),
        Podcast(
            4,
            "Judge John Hodgman",
            "https://maximumfun.org/wp-content/uploads/2023/01/JJHo-Logo-High-Res-400x400-1.jpg",
            "Only one can decide",
            [
                Episode(
                    605,
                    "Live from Seattle",
                    "Wed, February 15, 2023",
                ),
                Episode(604, "Live from Port Townsend, WA", "Thurs, Feb 9 2023"),
                Episode(603, "Acting in Bat Faith", "Wed, Feb 1 2023"),
            ],
        ),
    ]


def podcast(id: int) -> Podcast:
    return next(podcast for podcast in podcasts() if podcast.id == id)
