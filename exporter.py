import abc
import collections
import contextlib
import types
import typing

import common


class Exporter(contextlib.AbstractContextManager):

    def __enter__(self: typing.Self) -> typing.Self:
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        pass

    def _get_alternative_title(self: typing.Self, manga: common.Manga, language: str) -> str:
        for entry in manga.alternative_titles:
            if entry.language == language:
                return entry.title
        return ''

    @abc.abstractmethod
    def export(self: typing.Self, mangas: collections.abc.Iterable[common.Manga]) -> None:
        raise NotImplementedError('This method has not been implemented.')
