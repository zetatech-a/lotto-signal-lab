import pytest

from lotto_lab.cli import build_parser
from lotto_lab.models import Draw
from lotto_lab.recommend import recommend, select_strategy
from lotto_lab.strategy import UniformRandomStrategy


def make_draws(rounds: int = 260) -> list[Draw]:
    draws = []
    for round_no in range(1, rounds + 1):
        start = (round_no * 11) % 45
        numbers = tuple(sorted(((start + offset * 7) % 45) + 1 for offset in range(6)))
        bonus = next(number for number in range(1, 46) if number not in numbers)
        draws.append(Draw(round_no, numbers, bonus))
    return draws


def test_recommend_returns_unique_tickets() -> None:
    items = recommend(make_draws(), UniformRandomStrategy(), count=5, seed=42)
    assert len(items) == 5
    assert len({item.ticket for item in items}) == 5


def test_auto_selection_returns_a_valid_strategy() -> None:
    selection = select_strategy(
        make_draws(),
        min_history=200,
        simulations=100,
        seed=42,
    )
    ticket = selection.strategy.ticket(make_draws(), seed=1)
    assert len(ticket) == 6


def test_drift_is_not_a_recommendation_cli_choice() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["recommend", "--strategy", "drift"])
