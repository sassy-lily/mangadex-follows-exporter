from contextlib import AbstractContextManager
from time import perf_counter, sleep
from types import TracebackType
from typing import Self


class Throttler(AbstractContextManager):

    def __enter__(self: Self) -> Self:
        self._start = perf_counter()
        return self

    def __exit__(self: Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> bool | None:
        end = perf_counter()
        delta = end - self._start
        if delta < self._threshold:
            difference = self._threshold - delta
            sleep(difference)

    def __init__(self: Self, threshold: float) -> None:
        self._start = 0.0
        self._threshold = threshold
