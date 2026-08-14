# Prospective holdout policy

Rounds through 1236 are development data that have already been inspected during exploratory
strategy research. They must never be relabeled as pristine final holdout data.

Rounds 1237 and later are eligible for prospective holdout experiments. An experiment's complete
configuration should be committed before its holdout performance is revealed; Git history is part
of the experiment audit trail.

Each specification registers a fixed target horizon ending at `holdout_start_round +
min_holdout_rounds - 1`. Evaluation waits for that complete range and never expands the result to
later draws when the same specification is rerun. The local draw sequence from round 1 through the
registered horizon must also be complete so the walk-forward history is not truncated.

Registered holdouts require `min_history <= development_end_round` and at least two complete
periods (`min_holdout_rounds >= 2 * period_size`). The specification fingerprint includes the
evaluation protocol version and the complete canonical strategy manifest. Whenever strategy or
evaluation behavior changes in a way not represented by explicit manifest parameters, the
evaluation protocol version **must** change.

These controls are reproducibility and research-process guardrails, not a security boundary. The
software does not cryptographically prevent a researcher from inspecting the raw database.
