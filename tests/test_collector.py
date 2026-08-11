import httpx
import pytest

from lotto_lab.collector import (
    CollectorError,
    DhlotteryCollector,
    parse_latest_round,
    parse_legacy_payload,
)
from lotto_lab.models import Draw
from lotto_lab.storage import DrawRepository


def test_parse_latest_round() -> None:
    html = "<button>1236회</button><button>1235회</button>"
    assert parse_latest_round(html) == 1236


def test_latest_round_uses_win_number_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/lt645/winNumber"
        return httpx.Response(200, text="<option>1236회</option>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = DhlotteryCollector(client=client, delay_seconds=0)
    assert collector.latest_round() == 1236
    client.close()


def test_parse_legacy_payload() -> None:
    payload = {
        "returnValue": "success",
        "drwNo": 1236,
        "drwNoDate": "2026-08-08",
        "drwtNo1": 12,
        "drwtNo2": 18,
        "drwtNo3": 21,
        "drwtNo4": 29,
        "drwtNo5": 34,
        "drwtNo6": 38,
        "bnusNo": 10,
    }
    draw = parse_legacy_payload(payload)
    assert draw.round == 1236
    assert draw.numbers == (12, 18, 21, 29, 34, 38)
    assert draw.bonus == 10


def test_fetch_draw_rejects_mismatched_round() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "returnValue": "success",
                "drwNo": 2,
                "drwNoDate": "2002-12-14",
                **{f"drwtNo{i}": i for i in range(1, 7)},
                "bnusNo": 7,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = DhlotteryCollector(client=client, delay_seconds=0)
    with pytest.raises(CollectorError, match="returned round 2"):
        collector.fetch_draw(1)
    client.close()


def test_sync_repairs_missing_historical_round(tmp_path, monkeypatch) -> None:
    repository = DrawRepository(tmp_path / "lotto.db")
    repository.initialize()
    repository.upsert_many(
        [Draw(round_no, (1, 2, 3, 4, 5, 6), 7) for round_no in (1, 2, 4, 5)],
        source="test",
    )
    collector = DhlotteryCollector(client=httpx.Client(), delay_seconds=0)
    fetched: list[int] = []
    monkeypatch.setattr(collector, "latest_round", lambda: 5)

    def fetch_draw(round_no: int) -> Draw:
        fetched.append(round_no)
        return Draw(round_no, (1, 2, 3, 4, 5, 6), 7)

    monkeypatch.setattr(collector, "fetch_draw", fetch_draw)
    assert collector.sync(repository) == (5, 5)
    assert fetched == [3]
    assert repository.list_rounds() == [1, 2, 3, 4, 5]
    collector.client.close()
