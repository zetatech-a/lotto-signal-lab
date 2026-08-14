# Prospective holdout policy

Rounds through 1236 are development data that had already been inspected during exploratory
strategy research, making 1236/1237 the earliest permissible prospective boundary. They must
never be relabeled as pristine final holdout data.

Every newly authored experiment must freeze its own first unrevealed round. If rounds through `N`
are already known when a hypothesis is registered, its specification must set
`development_end_round = N` and `holdout_start_round = N + 1`. The complete specification must be
committed before those holdout outcomes are revealed; Git history provides the chronology and
audit trail.

Each specification registers a fixed target horizon ending at `holdout_start_round +
min_holdout_rounds - 1`. Evaluation waits for that complete range and never expands the result to
later draws when the same specification is rerun. The local draw sequence from round 1 through the
registered horizon must also be complete so the walk-forward history is not truncated.

Registered holdouts require at least 50 rounds, `min_history <= development_end_round`, and at
least two complete periods (`min_holdout_rounds >= 2 * period_size`). The specification
fingerprint includes the evaluation protocol version and the complete canonical strategy
manifest. Whenever strategy or evaluation behavior changes in a way not represented by explicit
manifest parameters, the evaluation protocol version **must** change.

These controls are reproducibility and research-process guardrails, not a security boundary. The
software cannot cryptographically prove that a researcher did not inspect raw draws before
committing the specification.
