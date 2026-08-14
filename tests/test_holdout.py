import json
from dataclasses import replace
from pathlib import Path

import pytest

from lotto_lab.cli import build_parser
from lotto_lab.holdout import (
    DEVELOPMENT_END_ROUND,
    PROSPECTIVE_HOLDOUT_START_ROUND,
    ExperimentSpec,
    evaluate_holdout,
    holdout_status,
    load_experiment_spec,
)
from lotto_lab.models import Draw
from lotto_lab.storage import DrawRepository
from lotto_lab.strategy import canonical_strategy_manifest


def spec_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "evaluation_protocol_version": 1,
        "experiment_id": "prospective-001",
        "development_end_round": 1236,
        "holdout_start_round": 1237,
        "min_holdout_rounds": 2,
        "strategies": ["uniform", "hot"],
        "strategy_manifest": {
            name: canonical_strategy_manifest(name) for name in ("uniform", "hot")
        },
        "seed_count": 2,
        "base_seed": 42,
        "min_history": 20,
        "period_size": 1,
        "primary_metric": "delta_mean_matches_mean",
        "hypothesis": "The candidate differs from uniform.",
        "decision_rule": "Interpret only after the registered minimum.",
    }
    payload.update(changes)
    if "strategies" in changes and "strategy_manifest" not in changes:
        payload["strategy_manifest"] = {
            name: canonical_strategy_manifest(name) for name in payload["strategies"]
        }
    return payload


def write_spec(path: Path, **changes: object) -> ExperimentSpec:
    path.write_text(json.dumps(spec_payload(**changes)), encoding="utf-8")
    return load_experiment_spec(path)


def make_draw(round_no: int) -> Draw:
    numbers = tuple(sorted((((round_no * 7) + offset * 5) % 45) + 1 for offset in range(6)))
    bonus = next(number for number in range(1, 46) if number not in numbers)
    return Draw(round_no, numbers, bonus)


def make_draws(end_round: int) -> list[Draw]:
    return [make_draw(round_no) for round_no in range(1, end_round + 1)]


def test_development_freeze_file_and_constants() -> None:
    freeze = json.loads(Path("research/development_freeze.json").read_text(encoding="utf-8"))
    assert DEVELOPMENT_END_ROUND == freeze["development_end_round"] == 1236
    assert PROSPECTIVE_HOLDOUT_START_ROUND == freeze["prospective_holdout_start_round"] == 1237


def test_valid_spec_loads_and_fingerprint_is_canonical(tmp_path: Path) -> None:
    first = write_spec(tmp_path / "first.json")
    reordered = dict(reversed(list(spec_payload().items())))
    (tmp_path / "second.json").write_text(json.dumps(reordered), encoding="utf-8")
    second = load_experiment_spec(tmp_path / "second.json")
    assert first == second
    assert first.fingerprint() == second.fingerprint()
    changed = ExperimentSpec.from_dict(spec_payload(base_seed=43))
    assert changed.fingerprint() != first.fingerprint()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": ""}, "experiment_id"),
        ({"strategies": ["uniform", "hot", "hot"]}, "duplicates"),
        ({"strategies": ["hot", "cold"]}, "uniform"),
        ({"holdout_start_round": 1238}, "holdout_start_round"),
        ({"min_history": 19}, "min_history must be >= 20"),
        ({"strategies": ["uniform", "drift"], "min_history": 299}, "drift"),
    ],
)
def test_invalid_specs_fail(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ExperimentSpec.from_dict(spec_payload(**changes))


def test_missing_and_malformed_specs_fail_clearly(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read experiment spec"):
        load_experiment_spec(path)
    payload = spec_payload()
    del payload["hypothesis"]
    with pytest.raises(ValueError, match="missing required fields: hypothesis"):
        ExperimentSpec.from_dict(payload)


def test_strategy_minimum_histories_are_accepted() -> None:
    assert ExperimentSpec.from_dict(spec_payload(min_history=20)).min_history == 20
    assert (
        ExperimentSpec.from_dict(
            spec_payload(strategies=["uniform", "drift"], min_history=300)
        ).min_history
        == 300
    )


def test_status_is_metadata_only_and_requires_contiguous_rounds() -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    result = holdout_status(list(range(1, 1239)), spec)
    assert result["available_holdout_rounds"] == 2
    assert result["ready_to_reveal"] is True
    assert set(result) == {
        "experiment_id",
        "experiment_spec_sha256",
        "development_end_round",
        "holdout_start_round",
        "holdout_end_round",
        "latest_stored_round",
        "available_holdout_rounds",
        "required_holdout_rounds",
        "ready_to_reveal",
    }
    assert not ({"mean_matches", "hit_3_plus_rate", "paired_delta"} & set(result))
    with pytest.raises(ValueError, match="missing=.*1237"):
        holdout_status([*range(1, 1237), 1238], spec)


@pytest.mark.parametrize("missing_round", [1000, 1236, 1237])
def test_status_rejects_any_gap_through_registered_horizon(missing_round: int) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    rounds = [round_no for round_no in range(1, 1239) if round_no != missing_round]
    with pytest.raises(ValueError, match=rf"missing=.*{missing_round}"):
        holdout_status(rounds, spec)


def test_complete_sequence_through_registered_holdout_end_succeeds() -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    assert holdout_status(list(range(1, 1239)), spec)["ready_to_reveal"] is True


def test_unready_evaluation_stops_before_trace_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload(min_holdout_rounds=2))
    called = False

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", forbidden)
    with pytest.raises(ValueError, match="requires 2 completed rounds; only 1"):
        evaluate_holdout(make_draws(1237), spec)
    assert called is False


def test_evaluation_targets_exact_holdout_without_resetting_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    draws = make_draws(1239)
    histories: list[tuple[int, ...]] = []

    from lotto_lab.strategy import FrequencyStrategy

    original = FrequencyStrategy.weights

    def recording(self: FrequencyStrategy, history: list[Draw]) -> dict[int, float]:
        histories.append(tuple(draw.round for draw in history))
        return original(self, history)

    monkeypatch.setattr(FrequencyStrategy, "weights", recording)
    result = evaluate_holdout(draws, spec)
    periods = result["evaluation"]["period_results"]["uniform"]
    assert periods[0]["target_round_start"] == 1237
    assert all(period["target_round_start"] > 1236 for period in periods)
    assert histories[-2] == tuple(range(1, 1237))
    assert histories[-1] == tuple(range(1, 1238))
    assert 1237 not in histories[-2]
    assert 1238 not in histories[-1]


def test_registered_horizon_is_immutable_and_later_targets_are_not_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    evaluated_ends: list[int] = []

    def recording_compare(draws: list[Draw], **kwargs: object) -> dict[str, object]:
        evaluated_ends.append(draws[-1].round)
        return {
            "target_rounds": [1237, 1238],
            "settings": kwargs,
            "round_details": {
                "target_rounds": [1237, 1238],
                "delta_mean_matches_vs_uniform": {"hot": [0.0, 0.0]},
            },
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", recording_compare)
    first = evaluate_holdout(make_draws(1239), spec)
    second = evaluate_holdout(make_draws(1240), spec)

    assert first == second
    assert first["holdout_end_round"] == 1238
    assert first["holdout_rounds"] == 2
    assert first["based_on_round"] == 1238
    assert first["evaluation"]["target_rounds"] == [1237, 1238]
    assert evaluated_ends == [1238, 1238]


def test_cli_invalid_spec_fails_before_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    called = False

    def repository(path: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("lotto_lab.cli._repository", repository)
    args = build_parser().parse_args(["holdout-evaluate", "--spec", str(path)])
    with pytest.raises(SystemExit, match="missing required fields"):
        args.func(args)
    assert called is False


def test_status_cli_reads_temporary_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path)
    repository = DrawRepository(tmp_path / "draws.db")
    repository.initialize()
    repository.upsert_many(make_draws(1238), source="test")
    args = build_parser().parse_args(
        ["holdout-status", "--spec", str(spec_path), "--db", str(repository.path)]
    )
    args.func(args)
    result = json.loads(capsys.readouterr().out)
    assert result["available_holdout_rounds"] == 2
    assert "evaluation" not in result


def test_non_object_spec_fails_cli_before_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "array.json"
    path.write_text("[]", encoding="utf-8")
    called = False

    def repository(path: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("lotto_lab.cli._repository", repository)
    for command in ("holdout-status", "holdout-evaluate"):
        args = build_parser().parse_args([command, "--spec", str(path)])
        with pytest.raises(SystemExit, match="must be a JSON object"):
            args.func(args)
    assert called is False


def test_min_history_cannot_skip_registered_targets() -> None:
    assert ExperimentSpec.from_dict(spec_payload(min_history=1236)).min_history == 1236
    with pytest.raises(ValueError, match="min_history must be <= development_end_round"):
        ExperimentSpec.from_dict(spec_payload(min_history=1237))


@pytest.mark.parametrize(
    ("rounds", "period_size", "accepted"),
    [(2, 1, True), (2, 2, False), (50, 25, True), (50, 26, False)],
)
def test_registered_holdout_requires_two_complete_periods(
    rounds: int, period_size: int, accepted: bool
) -> None:
    payload = spec_payload(min_holdout_rounds=rounds, period_size=period_size)
    if accepted:
        ExperimentSpec.from_dict(payload)
    else:
        with pytest.raises(ValueError, match=r"min_holdout_rounds must be >= 2 \* period_size"):
            ExperimentSpec.from_dict(payload)


def test_protocol_and_manifest_are_fingerprinted_and_validated() -> None:
    original = spec_payload()
    changed = spec_payload()
    changed_manifest = dict(changed["strategy_manifest"])
    changed_hot = dict(changed_manifest["hot"])
    changed_parameters = dict(changed_hot["parameters"])
    changed_parameters["z_to_log_weight"] = 0.07
    changed_hot["parameters"] = changed_parameters
    changed_manifest["hot"] = changed_hot
    changed["strategy_manifest"] = changed_manifest
    first = ExperimentSpec.from_dict(original)
    assert first.fingerprint() != replace(
        first, strategy_manifest=changed_manifest
    ).fingerprint()
    assert first.fingerprint() != replace(first, evaluation_protocol_version=2).fingerprint()
    with pytest.raises(ValueError, match="current strategy configuration"):
        ExperimentSpec.from_dict(changed)
    for manifest in (
        {"uniform": canonical_strategy_manifest("uniform")},
        {**original["strategy_manifest"], "cold": canonical_strategy_manifest("cold")},
    ):
        with pytest.raises(ValueError, match="keys must exactly match"):
            ExperimentSpec.from_dict({**original, "strategy_manifest": manifest})
    with pytest.raises(ValueError, match="unsupported evaluation_protocol_version"):
        ExperimentSpec.from_dict({**original, "evaluation_protocol_version": 2})


def test_evaluation_rejects_incomplete_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())

    def incomplete(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "round_details": {
                "target_rounds": [1238],
                "delta_mean_matches_vs_uniform": {"hot": [0.0]},
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", incomplete)
    with pytest.raises(ValueError, match="evaluation target range mismatch"):
        evaluate_holdout(make_draws(1238), spec)


def test_round_level_holdout_inference_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())

    def synthetic(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "round_details": {
                "target_rounds": [1237, 1238],
                "delta_mean_matches_vs_uniform": {"hot": [1.0, 3.0]},
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", synthetic)
    inference = evaluate_holdout(make_draws(1238), spec)["holdout_inference"]
    assert inference["method"] == "paired_round_normal_approximation_v1"
    result = inference["candidate_results"]["hot"]
    assert result == {
        "effect": 2.0,
        "standard_error": 1.0,
        "ci95_lower": pytest.approx(0.04),
        "ci95_upper": pytest.approx(3.96),
        "rounds": 2,
    }
