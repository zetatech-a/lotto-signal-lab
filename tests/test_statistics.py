import math

import pytest

from lotto_lab.models import Draw
from lotto_lab.statistics import (
    EXPECTED_LAST_SEEN_GAP,
    LAST_SEEN_GAP_STDDEV,
    LOTTO_NUMBER_OCCURRENCE_PROBABILITY,
    last_seen_gaps,
    number_counts,
    random_match_probabilities,
    standardized_frequency_drift_scores,
    standardized_last_seen_gap_scores,
)


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


def test_last_seen_gaps_count_completed_draws_since_appearance() -> None:
    draws = [
        Draw(1, (1, 2, 3, 4, 5, 6), 45),
        Draw(2, (2, 7, 8, 9, 10, 11), 45),
        Draw(3, (3, 12, 13, 14, 15, 16), 45),
    ]
    gaps = last_seen_gaps(draws)
    assert gaps[3] == 0
    assert gaps[2] == 1
    assert gaps[1] == 2


def test_last_seen_gap_is_left_censored_at_available_history_length() -> None:
    draws = [Draw(1, (1, 2, 3, 4, 5, 6), 45), Draw(2, (7, 8, 9, 10, 11, 12), 45)]
    assert last_seen_gaps(draws)[45] == len(draws)


def test_gap_null_constants_are_theoretical_not_estimated() -> None:
    probability = 6 / 45
    assert LOTTO_NUMBER_OCCURRENCE_PROBABILITY == probability
    assert EXPECTED_LAST_SEEN_GAP == (1 - probability) / probability
    assert LAST_SEEN_GAP_STDDEV == math.sqrt(1 - probability) / probability


def test_standardized_gap_score_direction() -> None:
    history = [Draw(index, (1, 2, 3, 4, 5, 6), 45) for index in range(1, 10)]
    scores = standardized_last_seen_gap_scores(history)
    assert scores[45] > 0
    assert scores[1] < 0


def make_partitioned_drift_history() -> list[Draw]:
    draws = []
    for index in range(300):
        numbers = [5, 6, 7, 8, 9, 10]
        if index < 250:
            numbers[0] = 4
            if index < 50:
                numbers[1] = 1
        else:
            numbers[0] = 3
            if index < 260:
                numbers[1] = 1
        draws.append(Draw(index + 1, tuple(sorted(numbers)), 45))
    return draws


def test_frequency_drift_uses_non_overlapping_50_and_250_windows() -> None:
    scores = standardized_frequency_drift_scores(make_partitioned_drift_history())
    assert scores[1] == pytest.approx(0.0)  # 10/50 == 50/250
    assert scores[2] == 0.0  # absent from both windows
    assert scores[3] > 0.0
    assert scores[4] < 0.0


def test_frequency_drift_ignores_history_before_trailing_300() -> None:
    history = make_partitioned_drift_history()
    older = [Draw(1, (1, 2, 3, 4, 11, 12), 45)]
    assert standardized_frequency_drift_scores(older + history) == (
        standardized_frequency_drift_scores(history)
    )


def test_frequency_drift_requires_complete_partition() -> None:
    with pytest.raises(ValueError, match="at least 300 prior draws"):
        standardized_frequency_drift_scores(make_partitioned_drift_history()[:-1])
