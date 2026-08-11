from lotto_lab.models import Draw
from lotto_lab.strategy import FrequencyStrategy, UniformRandomStrategy


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
