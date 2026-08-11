from lotto_lab.backtest import walk_forward_backtest
from lotto_lab.models import Draw
from lotto_lab.strategy import UniformRandomStrategy


def make_draws(rounds: int = 260) -> list[Draw]:
    draws = []
    for round_no in range(1, rounds + 1):
        start = ((round_no * 7) % 45)
        numbers = tuple(sorted(((start + offset * 5) % 45) + 1 for offset in range(6)))
        bonus = next(number for number in range(1, 46) if number not in numbers)
        draws.append(Draw(round_no, numbers, bonus))
    return draws


def test_walk_forward_backtest_runs() -> None:
    result = walk_forward_backtest(
        make_draws(),
        UniformRandomStrategy(),
        min_history=200,
        simulations=100,
        seed=42,
    )
    assert result.rounds == 60
    assert 0 <= result.mean_matches <= 6
    assert 0 <= result.monte_carlo_p_value <= 1
