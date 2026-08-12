import math

import pytest

from lotto_lab.backtest import BacktestObservation, walk_forward_trace
from lotto_lab.evaluation import compare_strategies, derive_seed
from lotto_lab.models import Draw
from lotto_lab.statistics import random_match_probabilities
from lotto_lab.strategy import FrequencyStrategy


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


def test_frequency_weights_are_computed_once_per_target_not_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    histories: list[tuple[int, ...]] = []
    original_weights = FrequencyStrategy.weights

    def recording_weights(
        self: FrequencyStrategy, history: list[Draw]
    ) -> dict[int, float]:
        histories.append(tuple(draw.round for draw in history))
        return original_weights(self, history)

    monkeypatch.setattr(FrequencyStrategy, "weights", recording_weights)
    compare_strategies(
        make_draws(),
        strategies=("uniform", "hot"),
        seed_count=2,
        min_history=20,
    )
    two_seed_histories = list(histories)
    histories.clear()
    compare_strategies(
        make_draws(),
        strategies=("uniform", "hot"),
        seed_count=7,
        min_history=20,
    )

    expected = [tuple(range(1, target_round)) for target_round in range(21, 32)]
    assert two_seed_histories == expected
    assert histories == expected


def test_uniform_paired_delta_is_zero() -> None:
    result = compare_strategies(
        make_draws(), strategies=("uniform",), seed_count=3, min_history=20
    )
    aggregate = result["aggregate_strategy_results"]["uniform"]
    assert aggregate["delta_mean_matches_mean"] == 0
    assert aggregate["candidate_equal_seed_fraction"] == 1


def test_candidate_deltas_pair_corresponding_seed_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    base_seed = 73
    run_seeds = [derive_seed(base_seed, index) for index in range(3)]
    matches_by_strategy_and_seed = {
        "uniform": dict(zip(run_seeds, (0, 1, 3))),
        "hot": dict(zip(run_seeds, (0, 0, 3))),
    }

    def fake_trace(
        draws: list[Draw], strategy: object, *, min_history: int, seed: int
    ) -> tuple[BacktestObservation, ...]:
        del draws, min_history
        strategy_name = getattr(strategy, "name")
        matches = matches_by_strategy_and_seed[strategy_name][seed]
        return (BacktestObservation(round=21, matches=matches),)

    monkeypatch.setattr("lotto_lab.evaluation.walk_forward_trace", fake_trace)
    monkeypatch.setattr(
        "lotto_lab.evaluation.build_strategy",
        lambda name: type("NamedStrategy", (), {"name": name})(),
    )
    result = compare_strategies(
        make_draws(),
        strategies=("uniform", "hot"),
        seed_count=3,
        base_seed=base_seed,
        min_history=20,
    )

    aggregate = result["aggregate_strategy_results"]["hot"]
    # Corresponding seed deltas are (0, -1, 0). Reordering the uniform runs,
    # such as reversing them, changes both this percentile and these fractions.
    assert aggregate["delta_mean_matches_p025"] == pytest.approx(-0.95)
    assert aggregate["candidate_equal_seed_fraction"] == pytest.approx(2 / 3)
    assert aggregate["candidate_worse_seed_fraction"] == pytest.approx(1 / 3)


def test_period_deltas_pair_corresponding_seed_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    base_seed = 91
    run_seeds = [derive_seed(base_seed, index) for index in range(3)]
    matches = {
        "uniform": dict(zip(run_seeds, ((0, 0), (1, 1), (3, 3)))),
        "hot": dict(zip(run_seeds, ((0, 0), (0, 0), (3, 3)))),
    }

    def fake_trace(
        draws: list[Draw], strategy: object, *, min_history: int, seed: int
    ) -> tuple[BacktestObservation, ...]:
        del draws, min_history
        values = matches[getattr(strategy, "name")][seed]
        return tuple(
            BacktestObservation(round=round_no, matches=value)
            for round_no, value in zip((21, 22), values)
        )

    monkeypatch.setattr("lotto_lab.evaluation.walk_forward_trace", fake_trace)
    monkeypatch.setattr(
        "lotto_lab.evaluation.build_strategy",
        lambda name: type("NamedStrategy", (), {"name": name})(),
    )
    result = compare_strategies(
        make_draws(),
        strategies=("uniform", "hot"),
        seed_count=3,
        base_seed=base_seed,
        min_history=20,
        period_size=2,
    )

    period = result["period_results"]["hot"][0]
    assert period["seed_runs"] == 3
    assert period["delta_mean_matches_vs_uniform_p025"] == pytest.approx(-0.95)
    assert period["candidate_equal_seed_fraction"] == pytest.approx(2 / 3)
    assert period["candidate_worse_seed_fraction"] == pytest.approx(1 / 3)


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
    assert periods[-1]["seed_runs"] == 2
    assert periods[-1]["delta_mean_matches_vs_uniform_p025"] == 0


def test_theoretical_baselines_use_exact_probabilities() -> None:
    result = compare_strategies(
        make_draws(), strategies=("uniform",), seed_count=1, min_history=20
    )
    baseline = result["theoretical_baselines"]
    assert baseline["theoretical_mean_matches"] == 0.8
    assert math.isclose(
        baseline["theoretical_hit_3_plus_rate"], sum(random_match_probabilities()[3:])
    )


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
