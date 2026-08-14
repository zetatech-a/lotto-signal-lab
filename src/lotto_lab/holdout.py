from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .evaluation import compare_strategies
from .models import Draw
from .strategy import build_strategy, canonical_strategy_manifest

DEVELOPMENT_END_ROUND = 1236
PROSPECTIVE_HOLDOUT_START_ROUND = 1237
SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_EVALUATION_PROTOCOL_VERSION = 1
SUPPORTED_PRIMARY_METRICS = {"delta_mean_matches_mean"}


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    schema_version: int
    evaluation_protocol_version: int
    experiment_id: str
    development_end_round: int
    holdout_start_round: int
    min_holdout_rounds: int
    strategies: tuple[str, ...]
    strategy_manifest: dict[str, dict[str, object]]
    seed_count: int
    base_seed: int
    min_history: int
    period_size: int
    primary_metric: str
    hypothesis: str
    decision_rule: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExperimentSpec:
        fields = tuple(cls.__dataclass_fields__)
        missing = [name for name in fields if name not in payload]
        extra = sorted(set(payload) - set(fields))
        if missing:
            raise ValueError(f"experiment spec missing required fields: {', '.join(missing)}")
        if extra:
            raise ValueError(f"experiment spec has unknown fields: {', '.join(extra)}")
        values = dict(payload)
        strategies = values["strategies"]
        if not isinstance(strategies, list) or not all(
            isinstance(name, str) for name in strategies
        ):
            raise ValueError("strategies must be a JSON array of strategy names")
        values["strategies"] = tuple(strategies)
        spec = cls(**values)
        spec.validate()
        return spec

    def validate(self) -> None:
        integer_fields = (
            "schema_version",
            "evaluation_protocol_version",
            "development_end_round",
            "holdout_start_round",
            "min_holdout_rounds",
            "seed_count",
            "base_seed",
            "min_history",
            "period_size",
        )
        for name in integer_fields:
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if self.evaluation_protocol_version != SUPPORTED_EVALUATION_PROTOCOL_VERSION:
            raise ValueError(
                "unsupported evaluation_protocol_version: "
                f"{self.evaluation_protocol_version}"
            )
        for name in ("experiment_id", "primary_metric", "hypothesis", "decision_rule"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.development_end_round < 1:
            raise ValueError("development_end_round must be >= 1")
        if self.holdout_start_round != self.development_end_round + 1:
            raise ValueError("holdout_start_round must equal development_end_round + 1")
        if (self.development_end_round, self.holdout_start_round) != (
            DEVELOPMENT_END_ROUND,
            PROSPECTIVE_HOLDOUT_START_ROUND,
        ):
            raise ValueError(
                "prospective boundary must be development round 1236 / holdout round 1237"
            )
        if self.min_holdout_rounds < 1:
            raise ValueError("min_holdout_rounds must be >= 1")
        if len(self.strategies) < 2:
            raise ValueError("strategies must contain at least two names")
        if len(set(self.strategies)) != len(self.strategies):
            raise ValueError("strategies must not contain duplicates")
        for name in self.strategies:
            try:
                build_strategy(name)
            except ValueError as error:
                raise ValueError(f"invalid strategy name: {name}") from error
        if "uniform" not in self.strategies:
            raise ValueError("strategies must include uniform as the paired baseline")
        if not isinstance(self.strategy_manifest, dict):
            raise ValueError("strategy_manifest must be a JSON object")
        expected_manifest = {
            name: canonical_strategy_manifest(name) for name in self.strategies
        }
        if set(self.strategy_manifest) != set(self.strategies):
            raise ValueError("strategy_manifest keys must exactly match strategies")
        if self.strategy_manifest != expected_manifest:
            raise ValueError("strategy_manifest does not match the current strategy configuration")
        if self.seed_count < 1:
            raise ValueError("seed_count must be >= 1")
        if self.min_history < 20:
            raise ValueError("min_history must be >= 20")
        if self.min_history > self.development_end_round:
            raise ValueError("min_history must be <= development_end_round")
        if "drift" in self.strategies and self.min_history < 300:
            raise ValueError("drift requires min_history >= 300")
        if self.period_size < 1:
            raise ValueError("period_size must be >= 1")
        if self.min_holdout_rounds < 2 * self.period_size:
            raise ValueError("min_holdout_rounds must be >= 2 * period_size")
        if self.primary_metric not in SUPPORTED_PRIMARY_METRICS:
            raise ValueError(f"unsupported primary_metric: {self.primary_metric}")

    def fingerprint(self) -> str:
        payload = asdict(self)
        payload["strategies"] = list(self.strategies)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_experiment_spec(path: str | Path) -> ExperimentSpec:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read experiment spec: {error}") from error
    if not isinstance(payload, dict):
        raise TypeError("experiment spec must be a JSON object")
    return ExperimentSpec.from_dict(payload)


def holdout_availability(rounds: list[int], spec: ExperimentSpec) -> tuple[int | None, int]:
    latest = max(rounds, default=None)
    if latest is None:
        return None, 0

    holdout_end_round = spec.holdout_start_round + spec.min_holdout_rounds - 1
    relevant_end_round = min(latest, holdout_end_round)
    stored_relevant_rounds = [number for number in rounds if number <= relevant_end_round]
    expected = list(range(1, relevant_end_round + 1))
    if stored_relevant_rounds != expected:
        missing = sorted(set(expected) - set(stored_relevant_rounds))
        duplicates = sorted(
            number
            for number in set(stored_relevant_rounds)
            if stored_relevant_rounds.count(number) > 1
        )
        raise ValueError(
            "stored draw rounds are not contiguous from round 1: "
            f"missing={missing[:20]}, duplicates={duplicates[:20]}"
        )
    available = max(0, relevant_end_round - spec.holdout_start_round + 1)
    return latest, available


def holdout_status(rounds: list[int], spec: ExperimentSpec) -> dict[str, object]:
    latest, available = holdout_availability(rounds, spec)
    holdout_end_round = spec.holdout_start_round + spec.min_holdout_rounds - 1
    return {
        "experiment_id": spec.experiment_id,
        "experiment_spec_sha256": spec.fingerprint(),
        "development_end_round": spec.development_end_round,
        "holdout_start_round": spec.holdout_start_round,
        "holdout_end_round": holdout_end_round,
        "latest_stored_round": latest,
        "available_holdout_rounds": available,
        "required_holdout_rounds": spec.min_holdout_rounds,
        "ready_to_reveal": available >= spec.min_holdout_rounds,
    }


def evaluate_holdout(draws: list[Draw], spec: ExperimentSpec) -> dict[str, object]:
    _, available = holdout_availability([draw.round for draw in draws], spec)
    if available < spec.min_holdout_rounds:
        raise ValueError(
            f"holdout requires {spec.min_holdout_rounds} completed rounds; only {available} are available"
        )
    holdout_end_round = spec.holdout_start_round + spec.min_holdout_rounds - 1
    registered_draws = [draw for draw in draws if draw.round <= holdout_end_round]
    evaluation = compare_strategies(
        registered_draws,
        strategies=spec.strategies,
        seed_count=spec.seed_count,
        base_seed=spec.base_seed,
        min_history=spec.min_history,
        period_size=spec.period_size,
        target_start_round=spec.holdout_start_round,
        include_round_details=True,
    )
    details = evaluation.pop("round_details")
    expected_rounds = list(range(spec.holdout_start_round, holdout_end_round + 1))
    actual_rounds = details["target_rounds"]
    if actual_rounds != expected_rounds or len(actual_rounds) != spec.min_holdout_rounds:
        raise ValueError(
            "evaluation target range mismatch: "
            f"expected {expected_rounds[0]}..{expected_rounds[-1]} "
            f"({spec.min_holdout_rounds} rounds), got {actual_rounds}"
        )
    inference: dict[str, dict[str, float | int]] = {}
    for name, deltas in details["delta_mean_matches_vs_uniform"].items():
        effect = statistics.fmean(deltas)
        standard_error = statistics.stdev(deltas) / math.sqrt(len(deltas))
        inference[name] = {
            "effect": effect,
            "standard_error": standard_error,
            "ci95_lower": effect - 1.96 * standard_error,
            "ci95_upper": effect + 1.96 * standard_error,
            "rounds": len(deltas),
        }
    return {
        "experiment_id": spec.experiment_id,
        "experiment_spec_sha256": spec.fingerprint(),
        "development_end_round": spec.development_end_round,
        "holdout_start_round": spec.holdout_start_round,
        "holdout_end_round": holdout_end_round,
        "holdout_rounds": spec.min_holdout_rounds,
        "based_on_round": holdout_end_round,
        "primary_metric": spec.primary_metric,
        "hypothesis": spec.hypothesis,
        "decision_rule": spec.decision_rule,
        "holdout_inference": {
            "method": "paired_round_normal_approximation_v1",
            "unit": "registered holdout round after averaging corresponding seed deltas",
            "metric": spec.primary_metric,
            "candidate_results": inference,
        },
        "interval_interpretation": (
            "Seed percentiles measure RNG seed variability conditional on the observed draws. "
            "The holdout inference interval measures round-level sampling uncertainty over the "
            "registered prospective outcomes. Neither guarantees future lottery performance."
        ),
        "evaluation": evaluation,
    }
