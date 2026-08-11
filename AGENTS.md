# AGENTS.md

## Mission

Ship a correct, reproducible Lotto 6/45 research codebase.

This repository does **not** assume that historical draw frequencies predict future draws.
Any claimed edge must survive strict out-of-sample walk-forward testing.

## Non-negotiable invariants

- Never use a target draw in its own features.
- Never label a result "better than random" from mean matches alone.
- Always report the random baseline and uncertainty/significance.
- Never hide collector failures or substitute third-party lottery data silently.
- Prefer the official `dhlottery.co.kr` source.
- Keep network request rates conservative and configurable.
- Never add lottery auto-purchase, credential automation, or payment automation.
- Never commit secrets, cookies, session tokens, or personal data.
- SQLite schema changes must be backward compatible or migrated explicitly.
- Keep deterministic seeds in tests.

## Commands before every PR

```bash
ruff check .
pytest
```

## Architecture boundaries

### collector.py
Owns all external website assumptions. A site markup/API change should not require edits to
statistics, strategy, backtest, recommendation, or storage modules.

### storage.py
Owns persistence. Draw rows are immutable facts identified by `round`.

### statistics.py
Descriptive statistics and null-hypothesis tests. No recommendation side effects.

### strategy.py
Maps historical draws to a ticket. Must consume historical draws only.

### backtest.py
Walk-forward evaluation. No data leakage. Every strategy must be comparable against uniform random.

### recommend.py
Generates reproducible candidate tickets. Must not claim guaranteed probability improvement.

## Collector change checklist

When changing the collector:

1. Verify official source behavior with a minimal real request.
2. Save the smallest sanitized fixture needed for regression tests.
3. Validate round number, six unique sorted values in 1..45, distinct bonus, and date if present.
4. Fail loudly on unexpected shapes.
5. Do not scrape more pages than necessary.
6. Preserve incremental sync.

## Statistical change checklist

When adding a feature/model:

1. State the hypothesis.
2. Add a baseline.
3. Add strict walk-forward evaluation.
4. Evaluate multiple time periods, not one lucky segment.
5. Report effect size and p-value/uncertainty.
6. If the result is not robust, keep it experimental or remove it.

## Scope guidance

Prefer small, testable changes. Do not introduce ML frameworks until transparent statistical
baselines have been exhausted and reproducibly beaten.
