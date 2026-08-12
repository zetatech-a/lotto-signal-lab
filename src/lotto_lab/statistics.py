from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from math import comb

from .models import Draw


@dataclass(frozen=True, slots=True)
class UniformityResult:
    draws: int
    chi_square: float
    monte_carlo_p_value: float
    simulations: int


def number_counts(draws: Iterable[Draw]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for draw in draws:
        counts.update(draw.numbers)
    for number in range(1, 46):
        counts.setdefault(number, 0)
    return counts


def standardized_occurrence_scores(
    draws: list[Draw], window: int
) -> dict[int, float]:
    """Return binomial z-scores from at most the trailing ``window`` draws."""
    if window < 1:
        raise ValueError("window must be >= 1")

    subset = draws[-window:]
    if not subset:
        return {number: 0.0 for number in range(1, 46)}

    counts = number_counts(subset)
    probability = 6 / 45
    expected = len(subset) * probability
    stddev = math.sqrt(len(subset) * probability * (1 - probability))
    return {
        number: (counts[number] - expected) / stddev
        for number in range(1, 46)
    }


def frequency_table(draws: list[Draw], window: int | None = None) -> list[tuple[int, int, float]]:
    if window is not None:
        if window < 1:
            raise ValueError("window must be >= 1")
        draws = draws[-window:]

    counts = number_counts(draws)
    total_slots = max(1, len(draws) * 6)
    return [
        (number, counts[number], counts[number] / total_slots)
        for number in range(1, 46)
    ]


def pair_counts(draws: Iterable[Draw]) -> Counter[tuple[int, int]]:
    pairs: Counter[tuple[int, int]] = Counter()
    for draw in draws:
        numbers = draw.numbers
        for left_index in range(5):
            for right_index in range(left_index + 1, 6):
                pairs[(numbers[left_index], numbers[right_index])] += 1
    return pairs


def last_seen_gaps(draws: list[Draw]) -> dict[int, int]:
    gaps = {number: len(draws) for number in range(1, 46)}
    for offset, draw in enumerate(reversed(draws)):
        for number in draw.numbers:
            if gaps[number] == len(draws):
                gaps[number] = offset
    return gaps


def chi_square_uniformity(draws: list[Draw]) -> float:
    if not draws:
        raise ValueError("at least one draw is required")
    counts = number_counts(draws)
    expected = len(draws) * 6 / 45
    return sum((counts[number] - expected) ** 2 / expected for number in range(1, 46))


def monte_carlo_uniformity_test(
    draws: list[Draw],
    *,
    simulations: int = 2000,
    seed: int = 0,
) -> UniformityResult:
    if not draws:
        raise ValueError("at least one draw is required")
    if simulations < 100:
        raise ValueError("simulations must be >= 100")

    observed = chi_square_uniformity(draws)
    rng = random.Random(seed)
    extreme = 0
    n_draws = len(draws)
    expected = n_draws * 6 / 45

    for _ in range(simulations):
        counts = [0] * 46
        for _ in range(n_draws):
            for number in rng.sample(range(1, 46), 6):
                counts[number] += 1
        simulated = sum(
            (counts[number] - expected) ** 2 / expected for number in range(1, 46)
        )
        if simulated >= observed:
            extreme += 1

    return UniformityResult(
        draws=n_draws,
        chi_square=observed,
        monte_carlo_p_value=(extreme + 1) / (simulations + 1),
        simulations=simulations,
    )


def random_match_probabilities() -> tuple[float, ...]:
    denominator = comb(45, 6)
    return tuple(
        comb(6, matches) * comb(39, 6 - matches) / denominator
        for matches in range(7)
    )
