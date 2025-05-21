import typing

import requests


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


def get_error(response: requests.Response) -> RuntimeError:
    error = RuntimeError('Request failed.')
    error.add_note(f'URL: {response.request.url}')
    error.add_note(f'Status: {response.status_code}')
    error.add_note(f'Content: {response.content}')
    return error
