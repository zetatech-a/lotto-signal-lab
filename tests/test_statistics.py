import pytest

from lotto_lab.models import Draw
from lotto_lab.statistics import number_counts, random_match_probabilities


def test_number_counts() -> None:
    draws = [
        Draw(1, (1, 2, 3, 4, 5, 6), 7),
        Draw(2, (1, 8, 9, 10, 11, 12), 13),
    ]
    counts = number_counts(draws)
    assert counts[1] == 2
    assert counts[45] == 0


def test_random_match_probabilities_sum_to_one() -> None:
    probabilities = random_match_probabilities()
    assert abs(sum(probabilities) - 1.0) < 1e-12
    assert sum(
        index * probability for index, probability in enumerate(probabilities)
    ) == pytest.approx(0.8)
