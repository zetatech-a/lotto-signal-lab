import math

import pytest

from lotto_lab.backtest import walk_forward_trace
from lotto_lab.evaluation import compare_strategies
from lotto_lab.models import Draw
from lotto_lab.statistics import random_match_probabilities


def make_draws(rounds: int = 31) -> list[Draw]:
    result = []
    for round_no in range(1, rounds + 1):
        numbers = tuple(sorted((((round_no * 7) + offset * 5) % 45) + 1 for offset in range(6)))
        bonus = next(number for number in range(1, 46) if number not in numbers)
        result.append(Draw(round_no, numbers, bonus))
    return result


class HistoryRecorder:
    name = "recorder"

    def __init__(self) -> None:
        self.histories: list[tuple[int, ...]] = []

    def ticket(self, history: list[Draw], *, seed: int) -> tuple[int, ...]:
        del seed
        self.histories.append(tuple(draw.round for draw in history))
        return (1, 2, 3, 4, 5, 6)


def test_trace_is_strict_walk_forward_and_never_resets_history() -> None:
    strategy = HistoryRecorder()
    trace = walk_forward_trace(make_draws(), strategy, min_history=20, seed=1)
    assert [item.round for item in trace] == list(range(21, 32))
    assert strategy.histories[0] == tuple(range(1, 21))
    assert strategy.histories[-1] == tuple(range(1, 31))
    assert all(target.round not in history for target, history in zip(trace, strategy.histories))


def test_comparison_is_deterministic_and_has_correct_seed_count() -> None:
    kwargs = dict(seed_count=4, base_seed=88, min_history=20, period_size=4)
    first = compare_strategies(make_draws(), **kwargs)
    second = compare_strategies(make_draws(), **kwargs)
    assert first == second
    assert all(
        result["seed_runs"] == 4
        for result in first["aggregate_strategy_results"].values()
    )


def test_different_base_seed_changes_stochastic_results() -> None:
    first = compare_strategies(make_draws(45), seed_count=3, base_seed=1, min_history=20)
    second = compare_strategies(make_draws(45), seed_count=3, base_seed=2, min_history=20)
    assert first["aggregate_strategy_results"] != second["aggregate_strategy_results"]


def test_uniform_paired_delta_is_zero() -> None:
    result = compare_strategies(
        make_draws(), strategies=("uniform",), seed_count=3, min_history=20
    )
    aggregate = result["aggregate_strategy_results"]["uniform"]
    assert aggregate["delta_mean_matches_mean"] == 0
    assert aggregate["candidate_equal_seed_fraction"] == 1


def test_periods_cover_targets_once_and_include_final_short_block() -> None:
    result = compare_strategies(
        make_draws(), strategies=("uniform",), seed_count=2, min_history=20, period_size=4
    )
    periods = result["period_results"]["uniform"]
    assert [(item["target_round_start"], item["target_round_end"]) for item in periods] == [
        (21, 24), (25, 28), (29, 31)
    ]
    covered = [
        round_no
        for item in periods
        for round_no in range(item["target_round_start"], item["target_round_end"] + 1)
    ]
    assert covered == list(range(21, 32))
    assert sum(item["target_rounds"] for item in periods) == 11


def test_theoretical_baselines_use_exact_probabilities() -> None:
    result = compare_strategies(
        make_draws(), strategies=("uniform",), seed_count=1, min_history=20
    )
    baseline = result["theoretical_baselines"]
    assert baseline["theoretical_mean_matches"] == 0.8
    assert math.isclose(baseline["theoretical_hit_3_plus_rate"], sum(random_match_probabilities()[3:]))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"seed_count": 0}, "seed_count"),
        ({"period_size": 0}, "period_size"),
        ({"strategies": ("hot",)}, "uniform"),
        ({"min_history": 31}, "not enough draws"),
    ],
)
def test_invalid_inputs(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compare_strategies(make_draws(), **kwargs)
