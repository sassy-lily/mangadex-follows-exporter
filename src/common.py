import typing


class Status(typing.NamedTuple):
    id: str
    status: str


class AlternativeTitle(typing.NamedTuple):
    language: str
    title: str


class ExternalLink(typing.NamedTuple):
    key: str
    value: str


class Manga(typing.NamedTuple):
    id: str
    type: str
    title_language: str
    title: str
    status: str
    alternative_titles: list[AlternativeTitle]
    external_links: list[ExternalLink]
    url: str
