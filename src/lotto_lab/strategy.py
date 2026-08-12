from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import ClassVar, Protocol

from .models import Draw
from .statistics import standardized_occurrence_scores

Ticket = tuple[int, int, int, int, int, int]


class Strategy(Protocol):
    name: str

    def ticket(self, history: list[Draw], *, seed: int) -> Ticket:
        ...


def _weighted_sample_without_replacement(
    weights: dict[int, float],
    *,
    count: int,
    rng: random.Random,
) -> tuple[int, ...]:
    available = dict(weights)
    selected: list[int] = []

    for _ in range(count):
        numbers = list(available)
        values = [max(0.0, available[number]) for number in numbers]
        total = sum(values)
        if total <= 0:
            chosen = rng.choice(numbers)
        else:
            chosen = rng.choices(numbers, weights=values, k=1)[0]
        selected.append(chosen)
        del available[chosen]

    return tuple(sorted(selected))


@dataclass(frozen=True, slots=True)
class UniformRandomStrategy:
    name: str = "uniform"

    def ticket(self, history: list[Draw], *, seed: int) -> Ticket:
        del history
        rng = random.Random(seed)
        return tuple(sorted(rng.sample(range(1, 46), 6)))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class FrequencyStrategy:
    mode: str = "hybrid"
    z_to_log_weight: float = 0.06
    max_log_tilt: float = 0.20
    name: str = "frequency"

    def __post_init__(self) -> None:
        if self.mode not in {"hot", "cold", "hybrid"}:
            raise ValueError("mode must be one of: hot, cold, hybrid")
        if self.z_to_log_weight < 0:
            raise ValueError("z_to_log_weight must be >= 0")
        if self.max_log_tilt < 0:
            raise ValueError("max_log_tilt must be >= 0")

    def _z_scores(self, history: list[Draw], window: int) -> dict[int, float]:
        return standardized_occurrence_scores(history, window)

    def scores(self, history: list[Draw]) -> dict[int, float]:
        if len(history) < 20:
            return {number: 0.0 for number in range(1, 46)}

        windows = [window for window in (20, 50, 100, 300) if window <= len(history)]
        window_weights = {20: 0.15, 50: 0.25, 100: 0.25, 300: 0.35}

        combined = {number: 0.0 for number in range(1, 46)}
        total_weight = sum(window_weights[window] for window in windows)

        for window in windows:
            z_scores = self._z_scores(history, window)
            weight = window_weights[window] / total_weight
            for number in range(1, 46):
                combined[number] += z_scores[number] * weight

        if self.mode == "cold":
            combined = {number: -score for number, score in combined.items()}
        elif self.mode == "hybrid":
            # Conservative shrinkage: historical deviations only produce a small tilt.
            combined = {number: 0.5 * score for number, score in combined.items()}

        return combined

    def weights(self, history: list[Draw]) -> dict[int, float]:
        """Compute the deterministic sampling weights for a history."""
        scores = self.scores(history)
        weights = {}
        for number in range(1, 46):
            raw_log_weight = scores[number] * self.z_to_log_weight
            log_weight = max(-self.max_log_tilt, min(self.max_log_tilt, raw_log_weight))
            weights[number] = math.exp(log_weight)
        return weights

    def ticket_from_weights(self, weights: dict[int, float], *, seed: int) -> Ticket:
        """Sample a ticket from precomputed weights using only the supplied seed."""
        rng = random.Random(seed)
        sampled = _weighted_sample_without_replacement(weights, count=6, rng=rng)
        return sampled  # type: ignore[return-value]

    def ticket(self, history: list[Draw], *, seed: int) -> Ticket:
        return self.ticket_from_weights(self.weights(history), seed=seed)


@dataclass(frozen=True, slots=True)
class FrequencyDriftStrategy(FrequencyStrategy):
    """Experiment using recent frequency deviation relative to a long baseline."""

    recent_window: ClassVar[int] = 50
    long_window: ClassVar[int] = 300
    name: str = "drift"

    def scores(self, history: list[Draw]) -> dict[int, float]:
        if len(history) < self.long_window:
            raise ValueError("drift requires at least 300 prior draws")

        recent = self._z_scores(history, self.recent_window)
        long = self._z_scores(history, self.long_window)
        return {number: recent[number] - long[number] for number in range(1, 46)}


def build_strategy(name: str) -> Strategy:
    if name == "uniform":
        return UniformRandomStrategy()
    if name in {"hot", "cold", "hybrid"}:
        return FrequencyStrategy(mode=name, name=name)
    if name == "drift":
        return FrequencyDriftStrategy()
    raise ValueError(f"unknown strategy: {name}")
