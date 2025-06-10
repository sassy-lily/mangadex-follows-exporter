from typing import NamedTuple


class Status(NamedTuple):
    id: str
    status: str


class AlternativeTitle(NamedTuple):
    language: str
    title: str


class ExternalLink(NamedTuple):
    key: str
    value: str


class Manga(NamedTuple):
    id: str
    type: str
    title_language: str
    title: str
    status: str
    alternative_titles: list[AlternativeTitle]
    external_links: list[ExternalLink]
    url: str


class Entry(NamedTuple):
    manga: Manga
    rating: float
    personal_rating: float | None
    status: str
