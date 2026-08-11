from __future__ import annotations

from dataclasses import dataclass

from .backtest import BacktestResult, walk_forward_backtest
from .models import Draw
from .strategy import Strategy, Ticket, UniformRandomStrategy, build_strategy


@dataclass(frozen=True, slots=True)
class Recommendation:
    ticket: Ticket
    seed: int


@dataclass(frozen=True, slots=True)
class StrategySelection:
    strategy: Strategy
    candidate_results: tuple[BacktestResult, ...]
    alpha: float
    corrected_alpha: float
    reason: str


def select_strategy(
    draws: list[Draw],
    *,
    min_history: int = 200,
    simulations: int = 2000,
    seed: int = 20260811,
    alpha: float = 0.05,
) -> StrategySelection:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    candidate_names = ("hot", "cold", "hybrid")
    results = tuple(
        walk_forward_backtest(
            draws,
            build_strategy(name),
            min_history=min_history,
            simulations=simulations,
            seed=seed,
        )
        for name in candidate_names
    )
    best = max(results, key=lambda result: result.mean_matches)

    # The best strategy was selected after testing 3 candidates. Use a simple
    # Bonferroni correction to avoid treating selection luck as evidence.
    corrected_alpha = alpha / len(candidate_names)
    if (
        best.mean_matches > best.random_expected_mean
        and best.monte_carlo_p_value <= corrected_alpha
    ):
        return StrategySelection(
            strategy=build_strategy(best.strategy),
            candidate_results=results,
            alpha=alpha,
            corrected_alpha=corrected_alpha,
            reason=(
                f"{best.strategy} passed the corrected random-baseline threshold "
                f"(p={best.monte_carlo_p_value:.6f} <= {corrected_alpha:.6f})"
            ),
        )

    return StrategySelection(
        strategy=UniformRandomStrategy(),
        candidate_results=results,
        alpha=alpha,
        corrected_alpha=corrected_alpha,
        reason=(
            "no candidate showed a statistically defensible advantage over uniform random "
            "after multiple-testing correction; using uniform"
        ),
    )


def recommend(
    draws: list[Draw],
    strategy: Strategy,
    *,
    count: int = 5,
    seed: int = 20260811,
) -> list[Recommendation]:
    if not draws:
        raise ValueError("at least one historical draw is required")
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")

    recommendations: list[Recommendation] = []
    seen: set[Ticket] = set()
    attempt = 0

    while len(recommendations) < count:
        ticket_seed = seed + attempt
        ticket = strategy.ticket(draws, seed=ticket_seed)
        if ticket not in seen:
            seen.add(ticket)
            recommendations.append(Recommendation(ticket=ticket, seed=ticket_seed))
        attempt += 1
        if attempt > count * 100:
            raise RuntimeError("could not generate enough unique tickets")

    return recommendations
