from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Draw
from .statistics import random_match_probabilities
from .strategy import Strategy


@dataclass(frozen=True, slots=True)
class BacktestResult:
    strategy: str
    rounds: int
    start_index: int
    mean_matches: float
    hit_3_plus_rate: float
    max_matches: int
    random_expected_mean: float
    monte_carlo_p_value: float
    simulations: int


@dataclass(frozen=True, slots=True)
class BacktestObservation:
    round: int
    matches: int


def _match_count(ticket: tuple[int, ...], draw: Draw) -> int:
    return len(set(ticket).intersection(draw.numbers))


def _random_mean_p_value(
    observed_mean: float,
    rounds: int,
    *,
    simulations: int,
    seed: int,
) -> float:
    probabilities = random_match_probabilities()
    values = tuple(range(7))
    rng = random.Random(seed)
    extreme = 0

    for _ in range(simulations):
        total = sum(rng.choices(values, weights=probabilities, k=rounds))
        if total / rounds >= observed_mean:
            extreme += 1

    return (extreme + 1) / (simulations + 1)


def walk_forward_backtest(
    draws: list[Draw],
    strategy: Strategy,
    *,
    min_history: int = 200,
    simulations: int = 5000,
    seed: int = 20260811,
) -> BacktestResult:
    if simulations < 100:
        raise ValueError("simulations must be >= 100")

    trace = walk_forward_trace(draws, strategy, min_history=min_history, seed=seed)
    matches = [observation.matches for observation in trace]

    mean_matches = sum(matches) / len(matches)
    return BacktestResult(
        strategy=strategy.name,
        rounds=len(matches),
        start_index=min_history,
        mean_matches=mean_matches,
        hit_3_plus_rate=sum(value >= 3 for value in matches) / len(matches),
        max_matches=max(matches),
        random_expected_mean=36 / 45,
        monte_carlo_p_value=_random_mean_p_value(
            mean_matches,
            len(matches),
            simulations=simulations,
            seed=seed ^ 0x5EED,
        ),
        simulations=simulations,
    )


def walk_forward_trace(
    draws: list[Draw],
    strategy: Strategy,
    *,
    min_history: int = 200,
    seed: int = 20260811,
    start_index: int | None = None,
) -> tuple[BacktestObservation, ...]:
    """Return per-target results using all, and only, preceding draws as history."""
    if min_history < 20:
        raise ValueError("min_history must be >= 20")
    if len(draws) <= min_history:
        raise ValueError("not enough draws for the requested min_history")

    first_index = min_history if start_index is None else max(min_history, start_index)
    if first_index >= len(draws):
        raise ValueError("no target draws in the requested evaluation range")

    observations: list[BacktestObservation] = []
    for index in range(first_index, len(draws)):
        # Strict walk-forward split: the target draw is never present in history.
        history = draws[:index]
        target = draws[index]
        ticket = strategy.ticket(history, seed=seed + target.round)
        observations.append(BacktestObservation(target.round, _match_count(ticket, target)))
    return tuple(observations)
