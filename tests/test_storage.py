from lotto_lab.models import Draw
from lotto_lab.storage import DrawRepository


def test_repository_round_trip(tmp_path) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert(Draw(1, (1, 2, 3, 4, 5, 6), 7), source="test")

    draws = repository.list_draws()
    assert len(draws) == 1
    assert draws[0].round == 1
