from lotto_lab.models import Draw
from lotto_lab.storage import DrawRepository


def test_repository_round_trip(tmp_path) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert(Draw(1, (1, 2, 3, 4, 5, 6), 7), source="test")

    draws = repository.list_draws()
    assert len(draws) == 1
    assert draws[0].round == 1
    assert repository.list_draw_sources() == {1: "test"}


def test_validate_integrity(tmp_path) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert_many(
        [Draw(1, (1, 2, 3, 4, 5, 6), 7), Draw(2, (2, 3, 4, 5, 6, 7), 8)],
        source="test",
    )
    assert repository.validate_integrity(2)["rows"] == 2


def test_validate_integrity_rejects_missing_round(tmp_path) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert(Draw(2, (2, 3, 4, 5, 6, 7), 8), source="test")

    try:
        repository.validate_integrity(2)
    except ValueError as exc:
        assert "missing=[1]" in str(exc)
    else:
        raise AssertionError("missing round was accepted")


def test_validate_integrity_reports_missing_and_extra_rounds(tmp_path) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert_many(
        [Draw(1, (1, 2, 3, 4, 5, 6), 7), Draw(3, (2, 3, 4, 5, 6, 7), 8)],
        source="test",
    )

    try:
        repository.validate_integrity(2)
    except ValueError as exc:
        assert "missing=[2]" in str(exc)
        assert "extra=[3]" in str(exc)
    else:
        raise AssertionError("missing and extra rounds were accepted")
