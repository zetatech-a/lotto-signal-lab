import json
from pathlib import Path

import httpx
import pytest

from lotto_lab.collector import (
    CollectorError,
    DhlotteryCollector,
    parse_draw_payload,
    parse_latest_round,
)
from lotto_lab.models import Draw
from lotto_lab.storage import DrawRepository

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_latest_round() -> None:
    html = "<button>1236회</button><button>1235회</button>"
    assert parse_latest_round(html) == 1236


def test_latest_round_uses_result_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/lt645/result"
        return httpx.Response(200, text="<option>1236회</option>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        collector = DhlotteryCollector(client=client, delay_seconds=0)
        assert collector.latest_round() == 1236


def test_parse_round_one_fixture() -> None:
    draw = parse_draw_payload(load_fixture("draw_round_1.json"), 1)
    assert draw == Draw(1, (10, 23, 29, 33, 37, 40), 16, draw_date=draw.draw_date)
    assert draw.draw_date.isoformat() == "2002-12-07"


def test_requested_row_is_selected_when_not_first_in_ten_row_window() -> None:
    draw = parse_draw_payload(load_fixture("draw_window_1236.json"), 1236)
    assert draw.numbers == (12, 18, 21, 29, 34, 38)
    assert draw.bonus == 10
    assert draw.draw_date.isoformat() == "2026-08-08"


def test_requested_round_missing_is_rejected() -> None:
    with pytest.raises(CollectorError, match="requested round 500 is missing"):
        parse_draw_payload(load_fixture("draw_window_1236.json"), 500)


@pytest.mark.parametrize(
    ("payload", "message"),
    [(None, "must be a JSON object"), ({"data": []}, "data must be an object")],
)
def test_malformed_response_containers_are_rejected(payload: object, message: str) -> None:
    with pytest.raises(CollectorError, match=message):
        parse_draw_payload(payload, 1)


@pytest.mark.parametrize("value", [None, {}, "not a list"])
def test_malformed_data_list_is_rejected(value: object) -> None:
    with pytest.raises(CollectorError, match=r"data\.list must be a list"):
        parse_draw_payload({"data": {"list": value}}, 1)


def test_invalid_date_is_rejected() -> None:
    payload = load_fixture("draw_round_1.json")
    payload["data"]["list"][0]["ltRflYmd"] = "20020230"
    with pytest.raises(CollectorError, match="valid YYYYMMDD"):
        parse_draw_payload(payload, 1)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("tm2WnNo", 10, "unique"), ("tm3WnNo", 46, "between 1 and 45")],
)
def test_duplicate_and_out_of_range_numbers_are_rejected(
    field: str, value: int, message: str
) -> None:
    payload = load_fixture("draw_round_1.json")
    payload["data"]["list"][0][field] = value
    with pytest.raises(CollectorError, match=message):
        parse_draw_payload(payload, 1)


def test_fetch_draw_uses_exact_path_query_and_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/lt645/selectPstLt645InfoNew.do"
        assert dict(request.url.params) == {"srchDir": "center", "srchLtEpsd": "1"}
        assert request.headers["Accept"] == "application/json, text/javascript, */*; q=0.01"
        assert request.headers["Ajax"] == "true"
        assert request.headers["X-Requested-With"] == "XMLHttpRequest"
        assert request.headers["Referer"] == "https://www.dhlottery.co.kr/lt645/result"
        return httpx.Response(200, json=load_fixture("draw_round_1.json"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        collector = DhlotteryCollector(client=client, delay_seconds=0)
        assert collector.fetch_draw(1).round == 1


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
