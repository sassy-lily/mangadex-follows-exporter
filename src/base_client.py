from abc import ABC
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Self

from requests import Response


class BaseClient(AbstractContextManager, ABC):

    def __enter__(self: Self) -> Self:
        return self

    def __exit__(self: Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> bool | None:
        pass

    @staticmethod
    def _get_error(response: Response) -> RuntimeError:
        error = RuntimeError('Request failed.')
        error.add_note(f'URL: {response.request.url}')
        error.add_note(f'Status: {response.status_code}')
        error.add_note(f'Content: {response.content}')
        return error
