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

WIN_NUMBER_PAGE_URL = "https://www.dhlottery.co.kr/lt645/winNumber"

# Compatibility endpoint used by older versions of the official site. Its continued
# availability is not assumed; unexpected responses fail loudly.
LEGACY_JSON_URL = "https://www.dhlottery.co.kr/common.do"

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


def parse_legacy_payload(payload: dict[str, object]) -> Draw:
    if str(payload.get("returnValue", "")).lower() != "success":
        raise CollectorError(f"official compatibility endpoint returned failure: {payload!r}")

    try:
        round_no = int(payload["drwNo"])
        numbers = tuple(sorted(int(payload[f"drwtNo{i}"]) for i in range(1, 7)))
        bonus = int(payload["bnusNo"])
        raw_date = str(payload.get("drwNoDate") or "")
        draw_date = date.fromisoformat(raw_date) if raw_date else None
    except (KeyError, TypeError, ValueError) as exc:
        raise CollectorError("unexpected draw payload shape") from exc

    return Draw(
        round=round_no,
        draw_date=draw_date,
        numbers=numbers,  # type: ignore[arg-type]
        bonus=bonus,
    )


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
        response = self._get(WIN_NUMBER_PAGE_URL)
        return parse_latest_round(response.text)

    def fetch_draw(self, round_no: int) -> Draw:
        if round_no < 1:
            raise ValueError("round_no must be >= 1")

        response = self._get(
            LEGACY_JSON_URL,
            params={"method": "getLottoNumber", "drwNo": round_no},
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CollectorError(
                "the official compatibility JSON endpoint is unavailable or changed; "
                "the current official per-round contract requires live verification"
            ) from exc

        if not isinstance(payload, dict):
            raise CollectorError("unexpected JSON response type")
        draw = parse_legacy_payload(payload)
        if draw.round != round_no:
            raise CollectorError(
                f"official endpoint returned round {draw.round} for requested round {round_no}"
            )
        return draw

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
