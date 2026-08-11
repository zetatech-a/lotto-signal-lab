from datetime import date

import pytest

from lotto_lab.models import Draw


def test_draw_accepts_valid_numbers() -> None:
    draw = Draw(1, (10, 23, 29, 33, 37, 40), 16, date(2002, 12, 7))
    assert draw.round == 1


def test_draw_rejects_duplicate_numbers() -> None:
    with pytest.raises(ValueError):
        Draw(1, (1, 2, 3, 4, 5, 5), 6)
