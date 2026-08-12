from unittest.mock import Mock

import pytest

from lotto_lab.cli import build_parser


@pytest.mark.parametrize(
    "arguments",
    [
        ["backtest", "--strategy", "drift", "--min-history", "299"],
        [
            "compare",
            "--strategies",
            "uniform",
            "drift",
            "--min-history",
            "299",
        ],
    ],
)
def test_drift_cli_rejects_insufficient_min_history_before_database_access(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Mock()
    monkeypatch.setattr("lotto_lab.cli._repository", repository)
    args = build_parser().parse_args(arguments)

    with pytest.raises(SystemExit, match="drift requires --min-history >= 300"):
        args.func(args)

    repository.assert_not_called()


@pytest.mark.parametrize("command", ["backtest", "compare"])
def test_gap_strategies_are_cli_choices(command: str) -> None:
    parser = build_parser()
    if command == "backtest":
        assert parser.parse_args([command, "--strategy", "gap-overdue"]).strategy == "gap-overdue"
    else:
        assert parser.parse_args(
            [command, "--strategies", "uniform", "gap-overdue", "gap-recent"]
        ).strategies == ["uniform", "gap-overdue", "gap-recent"]
