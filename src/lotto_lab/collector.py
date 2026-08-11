from __future__ import annotations

import csv
import re
import time
from datetime import date
from pathlib import Path
from typing import Self

import httpx
from bs4 import BeautifulSoup

from .models import Draw
from .storage import DrawRepository

RESULT_PAGE_URL = "https://www.dhlottery.co.kr/lt645/result"
DRAW_JSON_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
DRAW_JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Ajax": "true",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": RESULT_PAGE_URL,
}

ROUND_PATTERN = re.compile(r"^\s*(\d+)\s*회\s*$")


class CollectorError(RuntimeError):
    pass


def parse_latest_round(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    rounds: list[int] = []

    for element in soup.find_all(["button", "option", "a"]):
        text = element.get_text(" ", strip=True)
        match = ROUND_PATTERN.match(text)
        if match:
            rounds.append(int(match.group(1)))

    if not rounds:
        # Fallback for markup changes where round labels remain in page text.
        rounds = [int(value) for value in re.findall(r"\b(\d{1,5})\s*회\b", soup.get_text(" "))]

    if not rounds:
        raise CollectorError("could not detect the latest round from the official result page")
    return max(rounds)


def parse_draw_payload(payload: object, requested_round: int) -> Draw:
    """Parse the official site's current internal JSON response for one round."""
    if not isinstance(payload, dict):
        raise CollectorError("official draw response must be a JSON object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CollectorError("official draw response data must be an object")
    rows = data.get("list")
    if not isinstance(rows, list):
        raise CollectorError("official draw response data.list must be a list")

    row = next(
        (
            item
            for item in rows
            if isinstance(item, dict)
            and type(item.get("ltEpsd")) is int
            and item["ltEpsd"] == requested_round
        ),
        None,
    )
    if row is None:
        raise CollectorError(f"requested round {requested_round} is missing from data.list")

    raw_numbers = [row.get(f"tm{i}WnNo") for i in range(1, 7)]
    bonus = row.get("bnsWnNo")
    if any(type(number) is not int for number in raw_numbers):
        raise CollectorError("six integer winning numbers are required")
    if type(bonus) is not int:
        raise CollectorError("bonus must be an integer")

    raw_date = row.get("ltRflYmd")
    if not isinstance(raw_date, str) or re.fullmatch(r"[0-9]{8}", raw_date) is None:
        raise CollectorError("ltRflYmd must be a valid YYYYMMDD date")
    try:
        draw_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:]))
    except ValueError as exc:
        raise CollectorError("ltRflYmd must be a valid YYYYMMDD date") from exc

    try:
        numbers = tuple(sorted(raw_numbers))
        return Draw(
            round=requested_round,
            draw_date=draw_date,
            numbers=numbers,  # type: ignore[arg-type]
            bonus=bonus,
        )
    except ValueError as exc:
        raise CollectorError(f"invalid draw values for round {requested_round}: {exc}") from exc


class DhlotteryCollector:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        delay_seconds: float = 0.35,
        client: httpx.Client | None = None,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        self.delay_seconds = delay_seconds
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "lotto-signal-lab/0.1 "
                    "(research client; low-rate requests; contact via repository)"
                )
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _get(self, url: str, **kwargs: object) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = self.client.get(url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_seconds = min(float(retry_after), 10.0)
                    else:
                        sleep_seconds = 0.75 * (2**attempt)
                    if attempt < 2:
                        time.sleep(sleep_seconds)
                        continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.75 * (2**attempt))
                    continue

        raise CollectorError(f"request failed after retries: {url}") from last_error

    def latest_round(self) -> int:
        response = self._get(RESULT_PAGE_URL)
        return parse_latest_round(response.text)

    def fetch_draw(self, round_no: int) -> Draw:
        if round_no < 1:
            raise ValueError("round_no must be >= 1")

        response = self._get(
            DRAW_JSON_URL,
            params={"srchDir": "center", "srchLtEpsd": round_no},
            headers=DRAW_JSON_HEADERS,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CollectorError(
                "the official draw endpoint returned invalid JSON"
            ) from exc
        return parse_draw_payload(payload, round_no)

    def sync(self, repository: DrawRepository) -> tuple[int, int]:
        repository.initialize()
        latest = self.latest_round()
        stored_rounds = set(repository.list_rounds())
        missing_rounds = [
            round_no for round_no in range(1, latest + 1) if round_no not in stored_rounds
        ]
        for round_no in missing_rounds:
            draw = self.fetch_draw(round_no)
            repository.upsert(draw, source="dhlottery")
            if self.delay_seconds:
                time.sleep(self.delay_seconds)

        return repository.max_round() or 0, latest


def read_draws_csv(path: str | Path) -> list[Draw]:
    draws: list[Draw] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"round", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6", "bonus"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise CollectorError(
                "CSV columns must include: round,draw_date,n1,n2,n3,n4,n5,n6,bonus"
            )

        for row in reader:
            raw_date = (row.get("draw_date") or "").strip()
            numbers = tuple(sorted(int(row[f"n{i}"]) for i in range(1, 7)))
            draws.append(
                Draw(
                    round=int(row["round"]),
                    draw_date=date.fromisoformat(raw_date) if raw_date else None,
                    numbers=numbers,  # type: ignore[arg-type]
                    bonus=int(row["bonus"]),
                )
            )

    draws.sort(key=lambda draw: draw.round)
    return draws
