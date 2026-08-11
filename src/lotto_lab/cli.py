from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import walk_forward_backtest
from .collector import DhlotteryCollector, read_draws_csv
from .evaluation import compare_strategies
from .recommend import recommend, select_strategy
from .statistics import frequency_table, monte_carlo_uniformity_test
from .storage import DrawRepository
from .strategy import build_strategy

DEFAULT_DB = Path("data/lotto.db")


def _repository(path: str) -> DrawRepository:
    repository = DrawRepository(path)
    repository.initialize()
    return repository


def command_sync(args: argparse.Namespace) -> None:
    repository = _repository(args.db)
    with DhlotteryCollector(delay_seconds=args.delay) as collector:
        stored, latest = collector.sync(repository)
    print(json.dumps({"stored_through": stored, "latest": latest}, ensure_ascii=False))


def command_import_csv(args: argparse.Namespace) -> None:
    repository = _repository(args.db)
    draws = read_draws_csv(args.path)
    repository.upsert_many(draws, source=f"csv:{Path(args.path).name}")
    print(json.dumps({"imported": len(draws), "stored": repository.count()}, ensure_ascii=False))


def command_validate(args: argparse.Namespace) -> None:
    repository = _repository(args.db)
    with DhlotteryCollector(delay_seconds=0) as collector:
        official_latest = collector.latest_round()
    result = repository.validate_integrity(official_latest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_stats(args: argparse.Namespace) -> None:
    draws = _repository(args.db).list_draws()
    if not draws:
        raise SystemExit("database is empty; run sync or import-csv first")

    table = frequency_table(draws, window=args.window)
    ranked = sorted(table, key=lambda item: (-item[1], item[0]))
    result = {
        "draws": len(draws),
        "window": args.window,
        "top_10": ranked[:10],
        "bottom_10": list(reversed(ranked[-10:])),
    }
    if args.uniformity:
        result["uniformity"] = asdict(
            monte_carlo_uniformity_test(
                draws,
                simulations=args.simulations,
                seed=args.seed,
            )
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_backtest(args: argparse.Namespace) -> None:
    draws = _repository(args.db).list_draws()
    strategy = build_strategy(args.strategy)
    result = walk_forward_backtest(
        draws,
        strategy,
        min_history=args.min_history,
        simulations=args.simulations,
        seed=args.seed,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


def command_compare(args: argparse.Namespace) -> None:
    draws = _repository(args.db).list_draws()
    result = compare_strategies(
        draws,
        strategies=tuple(args.strategies),
        seed_count=args.seeds,
        base_seed=args.base_seed,
        min_history=args.min_history,
        period_size=args.period_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def command_recommend(args: argparse.Namespace) -> None:
    draws = _repository(args.db).list_draws()
    if not draws:
        raise SystemExit("database is empty; run sync or import-csv first")

    selection_payload = None
    if args.strategy == "auto":
        selection = select_strategy(
            draws,
            min_history=args.min_history,
            simulations=args.simulations,
            seed=args.seed,
        )
        strategy = selection.strategy
        selection_payload = {
            "reason": selection.reason,
            "alpha": selection.alpha,
            "corrected_alpha": selection.corrected_alpha,
            "candidates": [asdict(result) for result in selection.candidate_results],
        }
    else:
        strategy = build_strategy(args.strategy)

    items = recommend(draws, strategy, count=args.count, seed=args.seed)
    payload = {
        "requested_strategy": args.strategy,
        "selected_strategy": strategy.name,
        "based_on_round": draws[-1].round,
        "selection": selection_payload,
        "warning": (
            "Past draw statistics do not guarantee a higher future win probability. "
            "Treat these as reproducible statistical experiments, not predictions."
        ),
        "tickets": [
            {"numbers": item.ticket, "seed": item.seed}
            for item in items
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lotto-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="sync missing draws from the official website")
    sync.add_argument("--db", default=str(DEFAULT_DB))
    sync.add_argument("--delay", type=float, default=0.35)
    sync.set_defaults(func=command_sync)

    import_csv = subparsers.add_parser("import-csv", help="import a verified CSV fallback")
    import_csv.add_argument("path")
    import_csv.add_argument("--db", default=str(DEFAULT_DB))
    import_csv.set_defaults(func=command_import_csv)

    validate = subparsers.add_parser(
        "validate", help="validate stored draws against the official latest round"
    )
    validate.add_argument("--db", default=str(DEFAULT_DB))
    validate.set_defaults(func=command_validate)

    stats = subparsers.add_parser("stats", help="show frequency statistics")
    stats.add_argument("--db", default=str(DEFAULT_DB))
    stats.add_argument("--window", type=int)
    stats.add_argument("--uniformity", action="store_true")
    stats.add_argument("--simulations", type=int, default=2000)
    stats.add_argument("--seed", type=int, default=20260811)
    stats.set_defaults(func=command_stats)

    backtest = subparsers.add_parser("backtest", help="walk-forward backtest a strategy")
    backtest.add_argument("--db", default=str(DEFAULT_DB))
    backtest.add_argument(
        "--strategy",
        choices=["uniform", "hot", "cold", "hybrid"],
        default="hybrid",
    )
    backtest.add_argument("--min-history", type=int, default=200)
    backtest.add_argument("--simulations", type=int, default=5000)
    backtest.add_argument("--seed", type=int, default=20260811)
    backtest.set_defaults(func=command_backtest)

    compare = subparsers.add_parser(
        "compare", help="compare strategy stability across seeds and evaluation periods"
    )
    compare.add_argument("--db", default=str(DEFAULT_DB))
    compare.add_argument(
        "--strategies",
        nargs="+",
        choices=["uniform", "hot", "cold", "hybrid"],
        default=["uniform", "hot", "cold", "hybrid"],
    )
    compare.add_argument("--seeds", type=int, default=100)
    compare.add_argument("--base-seed", type=int, default=20260811)
    compare.add_argument("--min-history", type=int, default=200)
    compare.add_argument("--period-size", type=int, default=200)
    compare.set_defaults(func=command_compare)

    recommendation = subparsers.add_parser("recommend", help="generate reproducible tickets")
    recommendation.add_argument("--db", default=str(DEFAULT_DB))
    recommendation.add_argument(
        "--strategy",
        choices=["auto", "uniform", "hot", "cold", "hybrid"],
        default="auto",
    )
    recommendation.add_argument("--count", type=int, default=5)
    recommendation.add_argument("--min-history", type=int, default=200)
    recommendation.add_argument("--simulations", type=int, default=2000)
    recommendation.add_argument("--seed", type=int, default=20260811)
    recommendation.set_defaults(func=command_recommend)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
