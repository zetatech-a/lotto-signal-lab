import json
from dataclasses import replace
from pathlib import Path
from statistics import NormalDist

import pytest

from lotto_lab.cli import build_parser
from lotto_lab.holdout import (
    EARLIEST_DEVELOPMENT_END_ROUND,
    EARLIEST_PROSPECTIVE_HOLDOUT_START_ROUND,
    MIN_PROSPECTIVE_HOLDOUT_ROUNDS,
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
        "min_holdout_rounds": 50,
        "strategies": ["uniform", "hot"],
        "strategy_manifest": {
            name: canonical_strategy_manifest(name) for name in ("uniform", "hot")
        },
        "seed_count": 2,
        "base_seed": 42,
        "min_history": 20,
        "period_size": 25,
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


def directly_construct_spec(**changes: object) -> ExperimentSpec:
    payload = spec_payload(**changes)
    payload["strategies"] = tuple(payload["strategies"])
    return ExperimentSpec(**payload)


def write_spec(path: Path, **changes: object) -> ExperimentSpec:
    path.write_text(json.dumps(spec_payload(**changes)), encoding="utf-8")
    return load_experiment_spec(path)


def make_draw(round_no: int) -> Draw:
    numbers = tuple(sorted((((round_no * 7) + offset * 5) % 45) + 1 for offset in range(6)))
    bonus = next(number for number in range(1, 46) if number not in numbers)
    return Draw(round_no, numbers, bonus)


def make_draws(end_round: int) -> list[Draw]:
    return [make_draw(round_no) for round_no in range(1, end_round + 1)]


def make_sources(end_round: int, source: str = "dhlottery") -> dict[int, str]:
    return dict.fromkeys(range(1, end_round + 1), source)


def test_development_freeze_file_and_constants() -> None:
    freeze = json.loads(Path("research/development_freeze.json").read_text(encoding="utf-8"))
    assert EARLIEST_DEVELOPMENT_END_ROUND == freeze["development_end_round"] == 1236
    assert (
        EARLIEST_PROSPECTIVE_HOLDOUT_START_ROUND
        == freeze["prospective_holdout_start_round"]
        == 1237
    )
    assert MIN_PROSPECTIVE_HOLDOUT_ROUNDS == 50


def test_valid_spec_loads_and_fingerprint_is_canonical(tmp_path: Path) -> None:
    first = write_spec(tmp_path / "first.json")
    reordered = dict(reversed(list(spec_payload().items())))
    (tmp_path / "second.json").write_text(json.dumps(reordered), encoding="utf-8")
    second = load_experiment_spec(tmp_path / "second.json")
    assert first == second
    assert first.fingerprint() == second.fingerprint()
    changed = ExperimentSpec.from_dict(spec_payload(base_seed=43))
    assert changed.fingerprint() != first.fingerprint()


def test_direct_construction_validates_immediately() -> None:
    assert directly_construct_spec().experiment_id == "prospective-001"
    with pytest.raises(ValueError, match="min_holdout_rounds must be >= 50"):
        directly_construct_spec(min_holdout_rounds=49)


def test_replace_cannot_bypass_experiment_validation() -> None:
    spec = directly_construct_spec()
    with pytest.raises(ValueError, match="min_holdout_rounds must be >= 50"):
        replace(spec, min_holdout_rounds=49)
    with pytest.raises(ValueError, match="holdout_start_round"):
        replace(spec, holdout_start_round=1238)
    with pytest.raises(ValueError, match=r"min_holdout_rounds must be >= 2 \* period_size"):
        replace(spec, period_size=26)


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
    result = holdout_status(list(range(1, 1287)), spec)
    assert result["available_holdout_rounds"] == 50
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
    assert holdout_status(list(range(1, 1287)), spec)["ready_to_reveal"] is True


def test_unready_evaluation_stops_before_trace_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    called = False

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", forbidden)
    with pytest.raises(ValueError, match="requires 50 completed rounds; only 1"):
        evaluate_holdout(make_draws(1237), spec, draw_sources=make_sources(1237))
    assert called is False


def test_evaluation_targets_exact_holdout_without_resetting_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    draws = make_draws(1286)
    histories: list[tuple[int, ...]] = []

    from lotto_lab.strategy import FrequencyStrategy

    original = FrequencyStrategy.weights

    def recording(self: FrequencyStrategy, history: list[Draw]) -> dict[int, float]:
        histories.append(tuple(draw.round for draw in history))
        return original(self, history)

    monkeypatch.setattr(FrequencyStrategy, "weights", recording)
    result = evaluate_holdout(draws, spec, draw_sources=make_sources(1286))
    periods = result["evaluation"]["period_results"]["uniform"]
    assert periods[0]["target_round_start"] == 1237
    assert all(period["target_round_start"] > 1236 for period in periods)
    assert len(histories) == 50
    assert histories[0] == tuple(range(1, 1237))
    assert histories[1] == tuple(range(1, 1238))
    assert 1237 not in histories[0]
    assert 1238 not in histories[1]


def test_later_boundary_uses_all_prior_draws_and_never_its_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ExperimentSpec.from_dict(
        spec_payload(development_end_round=1300, holdout_start_round=1301)
    )
    histories: list[tuple[int, ...]] = []

    from lotto_lab.strategy import FrequencyStrategy

    original = FrequencyStrategy.weights

    def recording(self: FrequencyStrategy, history: list[Draw]) -> dict[int, float]:
        histories.append(tuple(draw.round for draw in history))
        return original(self, history)

    monkeypatch.setattr(FrequencyStrategy, "weights", recording)
    evaluate_holdout(make_draws(1350), spec, draw_sources=make_sources(1350))

    assert histories[0] == tuple(range(1, 1301))
    assert histories[1] == tuple(range(1, 1302))
    assert 1301 not in histories[0]
    assert 1302 not in histories[1]


def test_registered_horizon_is_immutable_and_later_targets_are_not_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    evaluated_ends: list[int] = []

    def recording_compare(draws: list[Draw], **kwargs: object) -> dict[str, object]:
        evaluated_ends.append(draws[-1].round)
        return {
            "target_rounds": list(range(1237, 1287)),
            "settings": kwargs,
            "round_details": {
                "target_rounds": list(range(1237, 1287)),
                "delta_mean_matches_vs_uniform": {"hot": [0.0] * 50},
            },
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", recording_compare)
    first = evaluate_holdout(make_draws(1287), spec, draw_sources=make_sources(1287))
    second = evaluate_holdout(make_draws(1288), spec, draw_sources=make_sources(1288))

    assert first == second
    assert first["holdout_end_round"] == 1286
    assert first["holdout_rounds"] == 50
    assert first["based_on_round"] == 1286
    assert first["evaluation"]["target_rounds"] == list(range(1237, 1287))
    assert evaluated_ends == [1286, 1286]


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
    repository.upsert_many(make_draws(1286), source="test")
    args = build_parser().parse_args(
        ["holdout-status", "--spec", str(spec_path), "--db", str(repository.path)]
    )
    args.func(args)
    result = json.loads(capsys.readouterr().out)
    assert result["available_holdout_rounds"] == 50
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
    ("development_end", "holdout_start", "accepted"),
    [(1236, 1237, True), (1300, 1301, True), (1235, 1236, False), (1300, 1302, False)],
)
def test_each_registration_freezes_its_own_prospective_boundary(
    development_end: int, holdout_start: int, accepted: bool
) -> None:
    payload = spec_payload(
        development_end_round=development_end,
        holdout_start_round=holdout_start,
    )
    if accepted:
        ExperimentSpec.from_dict(payload)
    else:
        with pytest.raises(ValueError):
            ExperimentSpec.from_dict(payload)


def test_registered_boundary_changes_fingerprint() -> None:
    initial = ExperimentSpec.from_dict(spec_payload())
    later = ExperimentSpec.from_dict(
        spec_payload(development_end_round=1300, holdout_start_round=1301)
    )
    assert initial.fingerprint() != later.fingerprint()


@pytest.mark.parametrize(
    ("rounds", "period_size", "accepted"),
    [(2, 1, False), (49, 1, False), (50, 25, True), (50, 26, False)],
)
def test_registered_holdout_requires_two_complete_periods(
    rounds: int, period_size: int, accepted: bool
) -> None:
    payload = spec_payload(min_holdout_rounds=rounds, period_size=period_size)
    if accepted:
        ExperimentSpec.from_dict(payload)
    else:
        message = (
            "min_holdout_rounds must be >= 50"
            if rounds < 50
            else r"min_holdout_rounds must be >= 2 \* period_size"
        )
        with pytest.raises(ValueError, match=message):
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
    with pytest.raises(ValueError, match="current strategy configuration"):
        replace(first, strategy_manifest=changed_manifest)
    with pytest.raises(ValueError, match="unsupported evaluation_protocol_version"):
        replace(first, evaluation_protocol_version=2)
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


@pytest.mark.parametrize("operation", ["fingerprint", "status", "evaluate"])
def test_mutated_manifest_is_rejected_at_public_boundaries(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    spec.strategy_manifest["hot"]["parameters"]["z_to_log_weight"] = 0.07

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid specs must be rejected before holdout processing")

    monkeypatch.setattr("lotto_lab.holdout.holdout_availability", forbidden)
    with pytest.raises(ValueError, match="current strategy configuration"):
        if operation == "fingerprint":
            spec.fingerprint()
        elif operation == "status":
            holdout_status([], spec)
        else:
            evaluate_holdout([], spec, draw_sources={})


def test_evaluation_rejects_incomplete_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())

    def incomplete(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "round_details": {
                "target_rounds": list(range(1238, 1287)),
                "delta_mean_matches_vs_uniform": {"hot": [0.0]},
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", incomplete)
    with pytest.raises(ValueError, match="evaluation target range mismatch"):
        evaluate_holdout(make_draws(1286), spec, draw_sources=make_sources(1286))


def test_round_level_holdout_inference_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())

    def synthetic(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "round_details": {
                "target_rounds": list(range(1237, 1287)),
                "delta_mean_matches_vs_uniform": {"hot": list(range(50))},
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", synthetic)
    inference = evaluate_holdout(make_draws(1286), spec, draw_sources=make_sources(1286))["holdout_inference"]
    assert inference["method"] == "paired_round_normal_approximation_bonferroni_v1_min50"
    assert inference["candidate_count"] == 1
    assert inference["critical_value"] == pytest.approx(NormalDist().inv_cdf(0.975))
    result = inference["candidate_results"]["hot"]
    assert result == {
        "effect": 24.5,
        "standard_error": pytest.approx(2.0615528128088303),
        "approx_familywise_ci95_lower": pytest.approx(20.45942918640784),
        "approx_familywise_ci95_upper": pytest.approx(28.54057081359216),
        "rounds": 50,
    }


def test_bonferroni_interval_widens_with_candidate_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def synthetic(*args: object, **kwargs: object) -> dict[str, object]:
        names = kwargs["strategies"]
        return {
            "round_details": {
                "target_rounds": list(range(1237, 1287)),
                "delta_mean_matches_vs_uniform": {
                    name: list(range(50)) for name in names if name != "uniform"
                },
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", synthetic)
    widths = []
    for strategies in (("uniform", "hot"), ("uniform", "hot", "cold")):
        spec = ExperimentSpec.from_dict(spec_payload(strategies=list(strategies)))
        inference = evaluate_holdout(
            make_draws(1286), spec, draw_sources=make_sources(1286)
        )["holdout_inference"]
        result = inference["candidate_results"]["hot"]
        widths.append(
            result["approx_familywise_ci95_upper"]
            - result["approx_familywise_ci95_lower"]
        )
        assert inference["candidate_count"] == len(strategies) - 1
        assert inference["per_candidate_alpha"] == pytest.approx(
            0.05 / (len(strategies) - 1)
        )
        assert inference["critical_value"] == pytest.approx(
            NormalDist().inv_cdf(1 - (0.05 / (len(strategies) - 1)) / 2)
        )
    assert widths[1] > widths[0]


def test_draw_provenance_is_preserved_and_compacted(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())

    def synthetic(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "round_details": {
                "target_rounds": list(range(1237, 1287)),
                "delta_mean_matches_vs_uniform": {"hot": [0.0] * 50},
            }
        }

    monkeypatch.setattr("lotto_lab.holdout.compare_strategies", synthetic)
    sources = make_sources(1287)
    for round_no in range(1240, 1287):
        sources[round_no] = "csv"
    sources[1287] = "ignored-after-horizon"
    result = evaluate_holdout(make_draws(1287), spec, draw_sources=sources)
    provenance = result["draw_provenance"]
    assert provenance["source_counts"] == {"csv": 47, "dhlottery": 1239}
    assert provenance["holdout_source_counts"] == {"csv": 47, "dhlottery": 3}
    assert provenance["holdout_all_preferred_official_source"] is False
    assert provenance["source_ranges"][-1] == {
        "round_start": 1240,
        "round_end": 1286,
        "source": "csv",
    }
    assert "ignored-after-horizon" not in str(provenance)


@pytest.mark.parametrize("sources", [{}, {1: ""}])
def test_missing_or_empty_draw_provenance_fails_explicitly(
    sources: dict[int, str],
) -> None:
    spec = ExperimentSpec.from_dict(spec_payload())
    with pytest.raises(ValueError, match="draw provenance is incomplete or invalid"):
        evaluate_holdout(make_draws(1286), spec, draw_sources=sources)
