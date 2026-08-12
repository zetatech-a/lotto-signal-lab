from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass

from .backtest import BacktestObservation, walk_forward_trace
from .models import Draw
from .statistics import random_match_probabilities
from .strategy import FrequencyStrategy, build_strategy

INTERVAL_INTERPRETATION = (
    "The 2.5th and 97.5th percentiles describe seed variability conditional on the "
    "observed historical draw sequence; they are not confidence intervals for future "
    "lottery performance."
)


@dataclass(frozen=True, slots=True)
class SeedMetrics:
    mean_matches: float
    hit_3_plus_rate: float


def derive_seed(base_seed: int, seed_index: int) -> int:
    """Derive a stable seed without consulting process-global random state."""
    payload = f"{base_seed}:{seed_index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    fraction = position - lower
    if fraction == 0:
        return ordered[lower]
    return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])


def _metrics(trace: tuple[BacktestObservation, ...]) -> SeedMetrics:
    return SeedMetrics(
        mean_matches=sum(item.matches for item in trace) / len(trace),
        hit_3_plus_rate=sum(item.matches >= 3 for item in trace) / len(trace),
    )


def _distribution(values: list[float], prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_mean": statistics.fmean(values),
        f"{prefix}_stddev": statistics.pstdev(values),
        f"{prefix}_p025": _percentile(values, 0.025),
        f"{prefix}_p975": _percentile(values, 0.975),
    }


def _period_slices(rounds: tuple[int, ...], period_size: int) -> list[tuple[int, int]]:
    return [
        (start, min(start + period_size, len(rounds)))
        for start in range(0, len(rounds), period_size)
    ]


def _frequency_traces(
    draws: list[Draw],
    strategy: FrequencyStrategy,
    run_seeds: list[int],
    *,
    min_history: int,
) -> list[tuple[BacktestObservation, ...]]:
    """Evaluate one frequency strategy while deriving each target's weights once."""
    runs: list[list[BacktestObservation]] = [[] for _ in run_seeds]
    for index in range(min_history, len(draws)):
        target = draws[index]
        weights = strategy.weights(draws[:index])
        for run, run_seed in zip(runs, run_seeds):
            ticket = strategy.ticket_from_weights(weights, seed=run_seed + target.round)
            matches = len(set(ticket).intersection(target.numbers))
            run.append(BacktestObservation(target.round, matches))
    return [tuple(run) for run in runs]


def compare_strategies(
    draws: list[Draw],
    *,
    strategies: tuple[str, ...] = ("uniform", "hot", "cold", "hybrid"),
    seed_count: int = 100,
    base_seed: int = 20260811,
    min_history: int = 200,
    period_size: int = 200,
) -> dict[str, object]:
    if seed_count <= 0:
        raise ValueError("seed_count must be > 0")
    if period_size <= 0:
        raise ValueError("period_size must be > 0")
    if "uniform" not in strategies:
        raise ValueError("strategies must include uniform as the paired baseline")
    if len(set(strategies)) != len(strategies):
        raise ValueError("strategies must not contain duplicates")
    if len(draws) <= min_history:
        raise ValueError("not enough draws for the requested min_history")

    traces: dict[str, list[tuple[BacktestObservation, ...]]] = {
        name: [] for name in strategies
    }
    run_seeds = [derive_seed(base_seed, seed_index) for seed_index in range(seed_count)]
    for name in strategies:
        strategy = build_strategy(name)
        if isinstance(strategy, FrequencyStrategy):
            traces[name] = _frequency_traces(
                draws, strategy, run_seeds, min_history=min_history
            )
        else:
            for run_seed in run_seeds:
                traces[name].append(
                    walk_forward_trace(
                        draws, strategy, min_history=min_history, seed=run_seed
                    )
                )

    metrics = {name: [_metrics(trace) for trace in runs] for name, runs in traces.items()}
    baseline = metrics["uniform"]
    aggregates: dict[str, dict[str, float | int]] = {}
    for name in strategies:
        runs = metrics[name]
        mean_values = [run.mean_matches for run in runs]
        hit_values = [run.hit_3_plus_rate for run in runs]
        mean_deltas = [run.mean_matches - base.mean_matches for run, base in zip(runs, baseline)]
        hit_deltas = [
            run.hit_3_plus_rate - base.hit_3_plus_rate
            for run, base in zip(runs, baseline)
        ]
        aggregates[name] = {
            "seed_runs": seed_count,
            **_distribution(mean_values, "mean_matches"),
            **_distribution(hit_values, "hit_3_plus_rate"),
            "delta_mean_matches_mean": statistics.fmean(mean_deltas),
            "delta_mean_matches_p025": _percentile(mean_deltas, 0.025),
            "delta_mean_matches_p975": _percentile(mean_deltas, 0.975),
            "delta_hit_3_plus_rate_mean": statistics.fmean(hit_deltas),
            "delta_hit_3_plus_rate_p025": _percentile(hit_deltas, 0.025),
            "delta_hit_3_plus_rate_p975": _percentile(hit_deltas, 0.975),
            "candidate_better_seed_fraction": sum(value > 0 for value in mean_deltas) / seed_count,
            "candidate_equal_seed_fraction": sum(value == 0 for value in mean_deltas) / seed_count,
            "candidate_worse_seed_fraction": sum(value < 0 for value in mean_deltas) / seed_count,
        }

    target_rounds = tuple(item.round for item in traces["uniform"][0])
    period_results: dict[str, list[dict[str, float | int]]] = {}
    for name in strategies:
        blocks = []
        for start, end in _period_slices(target_rounds, period_size):
            candidate_metrics = [_metrics(trace[start:end]) for trace in traces[name]]
            baseline_metrics = [_metrics(trace[start:end]) for trace in traces["uniform"]]
            mean_values = [run.mean_matches for run in candidate_metrics]
            hit_values = [run.hit_3_plus_rate for run in candidate_metrics]
            mean_deltas = [
                run.mean_matches - base.mean_matches
                for run, base in zip(candidate_metrics, baseline_metrics)
            ]
            hit_deltas = [
                run.hit_3_plus_rate - base.hit_3_plus_rate
                for run, base in zip(candidate_metrics, baseline_metrics)
            ]
            blocks.append(
                {
                    "target_round_start": target_rounds[start],
                    "target_round_end": target_rounds[end - 1],
                    "target_rounds": end - start,
                    "seed_runs": seed_count,
                    "mean_matches_mean": statistics.fmean(mean_values),
                    "hit_3_plus_rate_mean": statistics.fmean(hit_values),
                    "delta_mean_matches_vs_uniform_mean": statistics.fmean(mean_deltas),
                    "delta_mean_matches_vs_uniform_p025": _percentile(mean_deltas, 0.025),
                    "delta_mean_matches_vs_uniform_p975": _percentile(mean_deltas, 0.975),
                    "delta_hit_3_plus_rate_vs_uniform_mean": statistics.fmean(hit_deltas),
                    "delta_hit_3_plus_rate_vs_uniform_p025": _percentile(hit_deltas, 0.025),
                    "delta_hit_3_plus_rate_vs_uniform_p975": _percentile(hit_deltas, 0.975),
                    "candidate_better_seed_fraction": (
                        sum(value > 0 for value in mean_deltas) / seed_count
                    ),
                    "candidate_equal_seed_fraction": (
                        sum(value == 0 for value in mean_deltas) / seed_count
                    ),
                    "candidate_worse_seed_fraction": (
                        sum(value < 0 for value in mean_deltas) / seed_count
                    ),
                }
            )
        period_results[name] = blocks

    probabilities = random_match_probabilities()
    return {
        "based_on_round": draws[-1].round,
        "draw_count": len(draws),
        "min_history": min_history,
        "seed_count": seed_count,
        "base_seed": base_seed,
        "strategies": list(strategies),
        "period_size": period_size,
        "theoretical_baselines": {
            "theoretical_mean_matches": 0.8,
            "theoretical_hit_3_plus_rate": sum(probabilities[3:]),
        },
        "aggregate_strategy_results": aggregates,
        "period_results": period_results,
        "interval_interpretation": INTERVAL_INTERPRETATION,
    }
