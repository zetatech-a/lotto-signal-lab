import pytest

from lotto_lab.backtest import walk_forward_trace
from lotto_lab.models import Draw
from lotto_lab.strategy import (
    FrequencyDriftStrategy,
    FrequencyStrategy,
    UniformRandomStrategy,
    build_strategy,
)


def make_history(rounds: int = 250) -> list[Draw]:
    draws = []
    for round_no in range(1, rounds + 1):
        start = ((round_no - 1) * 6) % 45
        numbers = tuple(sorted(((start + offset) % 45) + 1 for offset in range(6)))
        bonus = next(number for number in range(1, 46) if number not in numbers)
        draws.append(Draw(round_no, numbers, bonus))
    return draws


def test_uniform_strategy_is_reproducible() -> None:
    strategy = UniformRandomStrategy()
    assert strategy.ticket([], seed=123) == strategy.ticket([], seed=123)


def test_frequency_strategy_returns_valid_ticket() -> None:
    ticket = FrequencyStrategy(mode="hybrid").ticket(make_history(), seed=123)
    assert len(ticket) == 6
    assert len(set(ticket)) == 6
    assert all(1 <= number <= 45 for number in ticket)


def test_frequency_ticket_is_preserved_after_weight_separation() -> None:
    strategy = FrequencyStrategy(mode="hot")
    history = make_history(37)
    assert strategy.ticket(history, seed=999) == (4, 7, 22, 26, 36, 40)
    assert strategy.ticket_from_weights(strategy.weights(history), seed=999) == (
        4,
        7,
        22,
        26,
        36,
        40,
    )


def test_frequency_sampling_varies_by_seed() -> None:
    strategy = FrequencyStrategy(mode="hybrid")
    weights = strategy.weights(make_history(37))
    assert strategy.ticket_from_weights(weights, seed=1) != strategy.ticket_from_weights(
        weights, seed=2
    )


def make_drift_history() -> list[Draw]:
    draws = []
    for round_no in range(1, 301):
        numbers = (2, 3, 4, 5, 6, 7) if round_no <= 250 else (1, 8, 9, 10, 11, 12)
        draws.append(Draw(round_no, numbers, 45))
    return draws


def test_drift_score_sign_matches_controlled_frequency_change() -> None:
    scores = FrequencyDriftStrategy().scores(make_drift_history())
    assert scores[1] > 0
    assert scores[2] < 0


def test_drift_requests_exact_recent_and_baseline_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = make_history(301)
    calls: list[tuple[tuple[int, ...], int, int]] = []

    def recording_scores(
        draws: list[Draw], *, recent_window: int, baseline_window: int
    ) -> dict[int, float]:
        calls.append((tuple(draw.round for draw in draws), recent_window, baseline_window))
        return {number: 0.0 for number in range(1, 46)}

    monkeypatch.setattr(
        "lotto_lab.strategy.standardized_frequency_drift_scores", recording_scores
    )
    FrequencyDriftStrategy().scores(history)

    assert calls == [(tuple(range(1, 302)), 50, 250)]


def test_drift_ignores_draws_older_than_long_window() -> None:
    history = make_drift_history()
    older = [Draw(round_no, (1, 13, 14, 15, 16, 17), 45) for round_no in range(1, 21)]
    assert FrequencyDriftStrategy().scores(older + history) == FrequencyDriftStrategy().scores(
        history
    )


def test_drift_is_strict_walk_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    histories: list[tuple[int, ...]] = []
    original = FrequencyDriftStrategy.ticket

    def recording_ticket(
        self: FrequencyDriftStrategy, history: list[Draw], *, seed: int
    ) -> tuple[int, ...]:
        histories.append(tuple(draw.round for draw in history))
        return original(self, history, seed=seed)

    monkeypatch.setattr(FrequencyDriftStrategy, "ticket", recording_ticket)
    walk_forward_trace(make_history(302), FrequencyDriftStrategy(), min_history=300, seed=4)
    assert histories == [tuple(range(1, 301)), tuple(range(1, 302))]
    assert 301 not in histories[0]
    assert 302 not in histories[1]


@pytest.mark.parametrize("operation", ["scores", "weights", "ticket"])
def test_drift_insufficient_history_fails_explicitly(operation: str) -> None:
    strategy = FrequencyDriftStrategy()
    with pytest.raises(ValueError, match="drift requires at least 300 prior draws"):
        if operation == "ticket":
            strategy.ticket(make_history(299), seed=1)
        else:
            getattr(strategy, operation)(make_history(299))


def test_drift_ticket_is_reproducible_stochastic_and_valid() -> None:
    strategy = FrequencyDriftStrategy()
    history = make_drift_history()
    ticket = strategy.ticket(history, seed=123)
    assert ticket == strategy.ticket(history, seed=123)
    assert ticket != strategy.ticket(history, seed=124)
    assert len(ticket) == len(set(ticket)) == 6
    assert all(1 <= number <= 45 for number in ticket)
    assert build_strategy("drift").name == "drift"
