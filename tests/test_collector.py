from lotto_lab.collector import parse_latest_round, parse_legacy_payload


def test_parse_latest_round() -> None:
    html = "<button>1236회</button><button>1235회</button>"
    assert parse_latest_round(html) == 1236


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
