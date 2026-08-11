from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Draw:
    round: int
    numbers: tuple[int, int, int, int, int, int]
    bonus: int
    draw_date: date | None = None

    def __post_init__(self) -> None:
        if self.round < 1:
            raise ValueError("round must be >= 1")
        if len(self.numbers) != 6:
            raise ValueError("exactly 6 winning numbers are required")
        if len(set(self.numbers)) != 6:
            raise ValueError("winning numbers must be unique")
        if tuple(sorted(self.numbers)) != self.numbers:
            raise ValueError("winning numbers must be sorted")
        if any(number < 1 or number > 45 for number in self.numbers):
            raise ValueError("winning numbers must be between 1 and 45")
        if self.bonus < 1 or self.bonus > 45:
            raise ValueError("bonus must be between 1 and 45")
        if self.bonus in self.numbers:
            raise ValueError("bonus must not duplicate a winning number")
