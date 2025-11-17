import csv
import os
from dataclasses import dataclass


@dataclass
class FifaAudience:
    country: str
    confederation: str
    population_share: str
    tv_audience_share: str
    gdp_weighted_share: str


@dataclass
class Paging:
    page: int
    perPage: int
    firstResult: int = 0
    lastResult: int = 0
    totalResults: int = 0

    @property
    def nextPage(self):
        return self.page + 1

    @property
    def prevPage(self):
        return self.page - 1

    @property
    def hasPrev(self):
        return self.page > 1

    @property
    def hasNext(self):
        return self.lastResult < self.totalResults


DATA = None


def _get_data() -> list[FifaAudience]:
    global DATA
    if DATA is None:
        DATA = [fa for fa in _read_data()]
    return DATA


def _read_data():
    dirname = os.path.dirname(__file__)
    fname = os.path.join(dirname, "fifa_countries_audience.csv")

    with open(fname) as csv_file:
        reader = csv.reader(csv_file, delimiter=",")
        next(reader)  # skip header
        for row in reader:
            yield FifaAudience(*row)


def list_items(paging: Paging) -> list[FifaAudience]:
    first = (paging.page - 1) * paging.perPage
    last = paging.page * paging.perPage

    paging.firstResult = first + 1
    paging.totalResults = len(_get_data())

    paging.lastResult = min(last, paging.totalResults)

    return _get_data()[first:last]
