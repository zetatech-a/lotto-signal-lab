# PAIR_V1_PREREGISTRATION.md

**Strategy:** `pair-v1`  
**Status:** FROZEN DESIGN  
**Purpose:** Pre-implementation hypothesis preregistration  
**Development diagnostic data:** rounds `1..1236`  
**Development evaluation targets:** rounds `331..1236`  
**Prospective experiment:** not yet instantiated  
**Primary objective:** test whether bounded positive historical pair co-occurrence weighting improves future mean match count relative to uniform random tickets under strict walk-forward evaluation.

---

## 1. Scope and research question

`pair-v1` tests exactly one hypothesis:

> Pairs of Lotto numbers that have co-occurred more often than expected under an IID uniform 6-of-45 null, measured over all prior rounds, may carry a weak positive signal that can be used to tilt ticket probabilities and improve future mean match count relative to a uniform random baseline.

`pair-v1` tests **positive/hot pair recurrence only**.

It does not test cold pairs, overdue pairs, recent pair momentum, rolling-window pair frequency, pair interactions beyond additive ticket weighting, or any optimized subset of pairs.

The strategy is one candidate strategy, not 990 independent hypotheses.

---

## 2. Formal hypothesis

For target round \(r\) and RNG seed \(s\), define

\[
M^{pair}_{r,s}
=
|T^{pair}_{r,s}\cap Y_r|
\]

and

\[
M^{uniform}_{r,s}
=
|T^{uniform}_{r,s}\cap Y_r|,
\]

where \(Y_r\) is the six winning numbers for round \(r\).

The bonus number is excluded.

Define paired match delta

\[
d_{r,s}
=
M^{pair}_{r,s}
-
M^{uniform}_{r,s}.
\]

Define round-level delta as the mean across registered seeds:

\[
d_r
=
\frac{1}{S}
\sum_{s=1}^{S}d_{r,s}.
\]

The population hypothesis is

\[
H_0:
E[d_r]\le0
\]

versus

\[
H_1:
E[d_r]>0.
\]

Although the scientific hypothesis is directional, prospective inference continues to use the repository's existing **two-sided familywise 95% confidence interval protocol**. No one-sided critical value is introduced for `pair-v1`.

---

## 3. Pair universe and input data

The number universe is

\[
\{1,2,\ldots,45\}.
\]

A pair is an unordered tuple

\[
e=(i,j),\qquad 1\le i<j\le45.
\]

The pair universe therefore contains

\[
\binom{45}{2}=990
\]

pairs.

Pairs must have one canonical order: ascending lexicographic order

\[
(1,2),(1,3),\ldots,(44,45).
\]

For every historical winning draw, exactly

\[
\binom62=15
\]

unordered pairs are generated from the six winning numbers.

The bonus number is never used for pair counts, pair scores, ticket weights, or the primary metric.

For a history containing \(n\) completed draws,

\[
\sum_e C_e=15n,
\]

where \(C_e\) is the historical co-occurrence count of pair \(e\).

---

## 4. Walk-forward history

For target round \(t\), the strategy may use exactly

\[
H_t=\{1,\ldots,t-1\}.
\]

No fixed rolling lookback window is used.

The history mode is therefore:

`expanding`

For target \(t\):

\[
n=t-1.
\]

The target draw itself and every later draw are forbidden from feature computation.

Examples:

\[
t=331
\Rightarrow
H_{331}=1..330
\]

and

\[
t=1236
\Rightarrow
H_{1236}=1..1235.
\]

The prospective holdout boundary does not reset feature history. A prospective target always uses every legally available previous draw.

There is no recency decay.

There is no date weighting.

There is no rolling-window selection.

---

## 5. Minimum history

`pair-v1` requires

\[
n\ge330.
\]

Therefore

`min_history = 330`.

This value is not selected from development performance.

Under the null probability defined below,

\[
E[C_e]=np_0.
\]

At \(n=330\),

\[
E[C_e]=330\times\frac1{66}=5.
\]

Thus 330 is fixed as the first history length for which the expected count of a fixed pair reaches 5.

The first eligible development target is consequently round `331`.

---

## 6. Null model

The null model is an IID sequence of fair Lotto 6/45 draws.

Each draw consists of six distinct numbers selected uniformly from 45.

For a fixed unordered pair \(e=(i,j)\), the probability that both numbers occur in a draw is

\[
p_0
=
\frac{\binom{43}{4}}
{\binom{45}{6}}
=
\frac6{45}\frac5{44}
=
\frac1{66}.
\]

For history length \(n\), the pair count under the null is therefore

\[
C_e
\sim
Binomial
\left(
n,\frac1{66}
\right).
\]

Its null expectation is

\[
E[C_e]=\frac n{66}
\]

and variance is

\[
Var(C_e)
=
n\frac1{66}\frac{65}{66}.
\]

Dependence between different pairs is explicitly acknowledged. The 990 pair counts are not treated as 990 independent statistical tests.

No pair-level p-value or pair-level significance claim is made.

The null model exists only to normalize historical co-occurrence into a feature score.

---

## 7. Raw pair score

For pair \(e\), let

\[
c=C_e
\]

and

\[
\hat p=\frac cn.
\]

Define the binomial log-likelihood deviance against

\[
p_0=\frac1{66}
\]

as

\[
G_e^2
=
2
\left[
c\ln
\left(
\frac{c}{np_0}
\right)
+
(n-c)\ln
\left(
\frac{n-c}{n(1-p_0)}
\right)
\right].
\]

The convention

\[
0\ln0=0
\]

must be used for boundary terms.

Define the signed root deviance

\[
r_e
=
sign(c-np_0)\sqrt{G_e^2}.
\]

If

\[
c=np_0,
\]

then

\[
r_e=0.
\]

`r_e` is a feature normalization statistic only.

It must not be interpreted as an individually corrected significance score for pair \(e\).

---

## 8. Positive-only score and clipping

`pair-v1` tests only positive historical co-occurrence.

The strategy score is

\[
s_e
=
\min
\left(
3,
\max(0,r_e)
\right).
\]

Therefore

\[
0\le s_e\le3.
\]

Any pair observed at or below its null expectation receives

\[
s_e=0.
\]

Any raw score above 3 is clipped to exactly 3.

There is no independently configurable threshold.

There is no top-k filtering.

There is no percentile filtering.

There is no normalization relative to the other 989 pairs.

There is no cross-sectional z-scoring or ranking.

---

## 9. Pair weight

Convert the clipped score to a positive pair weight using

\[
a_e
=
2^{s_e/3}.
\]

Therefore

\[
1\le a_e\le2.
\]

The exact reference values are

\[
s_e=0
\Rightarrow
a_e=1
\]

and

\[
s_e=3
\Rightarrow
a_e=2.
\]

No pair can receive more than twice the anchor weight of a null-or-negative pair.

The constants `3` and `2` are frozen.

They must not be optimized against development results.

---

## 10. Ticket-level weighting

A six-number ticket \(T\) contains exactly 15 unordered pairs.

Define its unnormalized pair score weight as

\[
W(T)
=
\frac1{15}
\sum_{\substack{e\subset T\\|e|=2}}
a_e.
\]

Because every pair weight lies in \([1,2]\),

\[
1\le W(T)\le2.
\]

The intended ticket distribution is

\[
P(T)
=
\frac{W(T)}
{\sum_{T'}W(T')}.
\]

No multiplicative pair-energy model is permitted.

In particular, the following type of weighting is outside `pair-v1`:

\[
\exp
\left(
\sum_{e\subset T}s_e
\right).
\]

The only permitted ticket-level combination rule is the **arithmetic mean of the 15 pair weights**.

---

## 11. Canonical sampling semantics

The ticket distribution above must be sampled using the following equivalent anchor-pair construction.

First define

\[
A=\sum_{e=1}^{990}a_e
\]

and

\[
q_e=\frac{a_e}{A}.
\]

One anchor pair \(e\) is sampled according to \(q_e\).

After selecting the two anchor numbers, exactly four additional distinct numbers are sampled uniformly without replacement from the remaining 43 numbers.

The resulting six numbers form the ticket.

The final ticket is represented in ascending numeric order.

For any ticket \(T\),

\[
P(T)
=
\frac{1}{\binom{43}{4}}
\sum_{e\subset T}
q_e
\]

which is

\[
P(T)
=
\frac{
\sum_{e\subset T}a_e
}{
\binom{43}{4}\sum_f a_f
}.
\]

This is proportional to the additive ticket weight defined above.

The sampled anchor pair is an internal sampling variable only. \(q_e\) must not be reported or interpreted as the final marginal probability that pair \(e\) appears in a ticket.

---

## 12. Uniform-reduction invariant

If every pair receives the same weight,

\[
a_e=1
\qquad
\forall e,
\]

then

\[
q_e=\frac1{990}.
\]

For every ticket,

\[
P(T)
=
\frac{15}
{990\binom{43}{4}}
=
\frac1{\binom{45}{6}}.
\]

Therefore an all-zero pair signal produces the exact **uniform distribution over all six-number tickets**.

This is distributional equivalence.

It does not require `pair-v1` and the repository's `uniform` strategy to produce the identical ticket for the same seed, because the two samplers may consume RNG state differently.

---

## 13. Frozen strategy parameters

| Parameter | Frozen value |
|---|---|
| strategy | `pair-v1` |
| direction | positive only |
| pair universe | all 990 unordered pairs |
| history mode | expanding |
| historical start | round 1 |
| min history | 330 draws |
| bonus used | no |
| null model | IID uniform 6-of-45 |
| null pair probability | `1/66` |
| pair score | signed root binomial deviance |
| negative score handling | clamp to 0 |
| score cap | `3.0` |
| pair weight | \(2^{s/3}\) |
| maximum pair weight | `2.0` |
| pair selection | no filtering; all 990 |
| ticket combination | arithmetic mean of 15 pair weights |
| ticket sampler | weighted anchor pair + uniform 4-of-43 fill |
| recency decay | none |
| rolling window | none |
| top-k | none |
| score threshold | none |
| temperature | none |
| smoothing/pseudocount | none |

These values define `pair-v1`.

Changing any behavior-affecting entry creates a different strategy and must not retain the `pair-v1` research identity.

---

## 14. RNG and reproducibility contract

Evaluation uses the existing repository deterministic seed derivation and paired multi-seed framework.

The registered values are:

`seed_count = 100`

`base_seed = 0`

Each candidate observation is paired with the corresponding uniform observation for the same target round and registered seed identity.

The implementation must be deterministic under the repository's supported runtime.

Repeated execution with identical input data, strategy implementation, ExperimentSpec, and seed must reproduce the same ticket trace.

Pathwise equality between `pair-v1` and `uniform` is not required.

---

## 15. Primary metric

The registered ExperimentSpec primary metric is

`delta_mean_matches_mean`.

For ticket \(T\) and winning-number set \(Y\), the raw ticket-level outcome is

\[
M(T,Y)=|T\cap Y|.
\]

Thus the raw outcome

\[
M\in\{0,1,2,3,4,5,6\}.
\]

The registered primary metric `delta_mean_matches_mean` is the mean paired difference in this raw match outcome between `pair-v1` and `uniform`, using the round-level and seed-level aggregation defined below. The raw ticket-level outcome `matches` is not itself the registered primary metric.

Bonus matches, prize tiers, jackpot amount, monetary return, ticket sales, and payout size are not part of either the raw outcome or the primary metric.

The primary metric must not be changed after development results are observed.

---

## 16. Development evaluation dataset

The historical development dataset is permanently fixed at rounds

\[
1..1236.
\]

Because `min_history = 330`, eligible target rounds are

\[
331..1236.
\]

The number of eligible development target rounds is therefore

\[
R=906.
\]

Every target is evaluated strict walk-forward:

\[
history(t)=1..t-1.
\]

Rounds after 1236 must never be appended to the `pair-v1` development diagnostic dataset.

They may only belong to excluded pre-registration history or a formally registered prospective holdout, depending on registration timing.

---

## 17. Development comparison

Exactly two strategies are compared:

`uniform`

and

`pair-v1`.

No alternate pair candidate is included in the `pair-v1` development experiment.

For each target \(r\) and seed \(s\),

\[
d_{r,s}
=
M^{pair}_{r,s}
-
M^{uniform}_{r,s}.
\]

For every development target round, define the round-level delta by averaging over the 100 registered paired seeds:

\[
d_r
=
\frac1{100}
\sum_{s=1}^{100}d_{r,s}.
\]

Overall development delta is

\[
\Delta_{dev}
=
\frac1R
\sum_{r=331}^{1236}d_r,
\qquad R=906.
\]

Let \(s_{d,dev}\) be the sample standard deviation of the 906 round-level deltas \(d_r\). Define

\[
SE_{dev}
=
\frac{s_{d,dev}}{\sqrt{R}}
\]

and

\[
L_{dev}
=
\Delta_{dev}
-
1.95996398454\,SE_{dev}.
\]

The corresponding interval \(\Delta_{dev}\pm1.95996398454\,SE_{dev}\) is a two-sided approximate 95% round-level uncertainty interval. It is a development diagnostic, not prospective confirmation; the 100 seeds are paired simulation replicates and are not treated as independent future observations.

For each seed,

\[
\Delta_s
=
\frac1R
\sum_r d_{r,s}.
\]

Development periods are consecutive 50-target blocks beginning with target 331.

The 18 complete blocks are therefore:

`331..380`

through

`1181..1230`.

The remaining targets

`1231..1236`

are included in the overall and seed-level metrics but excluded from the full-period stability criterion.

---

## 18. Development decision rule

`pair-v1` passes the development diagnostic only if all three conditions hold:

\[
L_{dev}>0
\]

and

\[
median_s(\Delta_s)>0
\]

and at least 10 of the 18 complete 50-round development periods have positive paired mean delta.

Equivalently,

\[
\#\{positive\ full\ periods\}\ge10.
\]

Equality with zero does not count as positive.

These criteria, including the uncertainty-bound condition, are a development gate, not confirmatory statistical evidence or prospective confirmation.

No development p-value is required for promotion.

If any one of the three conditions fails, `pair-v1` is classified:

`DEVELOPMENT_NOT_SUPPORTED`

and `pair-v1` does not proceed to prospective promotion testing.

---

## 19. Permitted development reporting

Development reporting may contain aggregate candidate mean, aggregate uniform mean, paired overall delta, per-seed deltas, seed median, seed variability summaries, better/equal/worse seed fractions, and the predefined 50-round period deltas.

The following analyses must not be used to modify or rescue `pair-v1`:

- rolling-window sweeps;
- score-cap sweeps;
- max-weight sweeps;
- hot-versus-cold direction selection;
- top-k pair selection;
- pair-level significance filtering;
- pair leaderboard-based selection;
- score-threshold optimization;
- recency-decay optimization;
- alternative ticket-combination searches;
- alternate primary metrics;
- seed-count optimization;
- favorable historical subperiod selection;
- removal of unfavorable rounds;
- parameter choice based on `331..1236` performance.

Such analyses may motivate a separately named future hypothesis such as `pair-v2`, but they cannot alter `pair-v1`.

---

## 20. Prospective registration timing

The mathematical and behavioral definition of `pair-v1` is frozen by this document.

However, the prospective holdout boundary is not assigned until all of the following have occurred:

1. the implementation conforms to this document;
2. required invariant and regression tests pass;
3. the development diagnostic is executed exactly once for the registered `pair-v1` definition;
4. the development decision rule passes;
5. the final strategy manifest and implementation identity are available for fingerprinting.

Let \(N\) be the latest Lotto round whose result is already publicly available when the final prospective ExperimentSpec and its fingerprint are committed.

The prospective boundary is then mechanically defined as

\[
development\_end\_round=N
\]

and

\[
holdout\_start\_round=N+1.
\]

Therefore the prospective start round is **not a tunable pair-v1 parameter**.

A round whose result was already public before the final prospective registration commit cannot become pristine `pair-v1` holdout data.

---

## 21. Prospective ExperimentSpec constants

Once the boundary is instantiated, the prospective ExperimentSpec must use:

| Field | Value |
|---|---|
| strategies | exactly `uniform`, `pair-v1` |
| non-uniform candidate count | `1` |
| seed_count | `100` |
| base_seed | `0` |
| min_history | `330` |
| period_size | `50` |
| min_holdout_rounds | `100` |
| primary_metric | `delta_mean_matches_mean` |
| evaluation_protocol_version | `1` |
| holdout start | \(N+1\) |
| holdout end | \(N+100\) |

The registered prospective range therefore contains exactly 100 rounds.

The value `1` is the repository's existing machine-readable ExperimentSpec protocol identifier.
References to `v0.4` describe the repository/guardrail milestone, not an ExperimentSpec protocol
identifier. This registration uses the existing protocol semantics and does not define a new
evaluation protocol version.

If

\[
H=holdout\_start\_round,
\]

then the evaluation range is

\[
H..H+99.
\]

Later database rows must not extend this experiment's evaluation horizon.

---

## 22. No prospective peeking

Before all 100 registered holdout rounds are available, performance output is forbidden.

`holdout-status` may expose readiness metadata only.

It must not expose pair-v1 match counts, uniform match counts, deltas, partial period results, confidence intervals, direction of effect, or any other performance signal.

There is no evaluation at round 50.

There is no sequential stopping.

There is no extension from 100 to 150 rounds based on an unfavorable or borderline result.

The registered 100-round horizon is evaluated once.

---

## 23. Prospective estimator

For each registered holdout round \(r\),

\[
d_r
=
\frac1{100}
\sum_{s=1}^{100}
\left(
M^{pair}_{r,s}
-
M^{uniform}_{r,s}
\right).
\]

The prospective effect estimate is

\[
\hat\delta
=
\frac1{100}
\sum_{r=1}^{100}d_r.
\]

Let

\[
s_d
\]

be the sample standard deviation of the 100 round-level deltas.

Then

\[
SE
=
\frac{s_d}{\sqrt{100}}.
\]

The independent observational unit for inference is the holdout round.

The 100 RNG seeds are not treated as 100 independent future observations.

---

## 24. Prospective confidence interval

There is exactly one non-uniform candidate:

\[
m=1.
\]

The existing protocol uses familywise

\[
\alpha=0.05.
\]

Therefore Bonferroni adjustment leaves

\[
\alpha_{candidate}=0.05.
\]

The two-sided critical value is

\[
z^*
=
\Phi^{-1}(0.975)
\approx
1.95996398454.
\]

The prospective 95% interval is

\[
CI
=
\hat\delta
\pm
z^*SE.
\]

The lower endpoint is

\[
L
=
\hat\delta
-
1.95996398454SE.
\]

---

## 25. Prospective period stability

The 100-round holdout contains exactly two predefined 50-round periods.

If the holdout begins at \(H\), define

\[
B_1=H..H+49
\]

and

\[
B_2=H+50..H+99.
\]

For each block,

\[
\Delta_{B_k}
=
\frac1{50}
\sum_{r\in B_k}d_r.
\]

No alternative block boundary may be selected after results are observed.

---

## 26. Final prospective decision rule

`pair-v1` is classified as

`PROSPECTIVELY_SUPPORTED`

if and only if all three conditions hold:

\[
L>0
\]

and

\[
\Delta_{B_1}>0
\]

and

\[
\Delta_{B_2}>0.
\]

That is,

\[
\boxed{
\hat\delta
-
1.95996398454SE
>0
}
\]

AND

\[
\boxed{
\Delta_{B_1}>0
}
\]

AND

\[
\boxed{
\Delta_{B_2}>0
}.
\]

If any condition fails or equals zero, the strategy is classified:

`PROSPECTIVELY_NOT_SUPPORTED`.

There is no post-hoc “near miss”, “promising”, “borderline”, or extended-horizon promotion category.

Seed percentile, better-seed fraction, or other RNG robustness summaries may be reported as descriptive metadata but cannot override this decision rule.

---

## 27. Recommendation eligibility

Passing development diagnostics alone does not make `pair-v1` recommendation-eligible.

Only `PROSPECTIVELY_SUPPORTED` status can make the strategy eligible for a separate recommendation/promotion decision.

Prospective support establishes evidence under this experiment protocol only.

It does not establish that lottery draws are predictable, that pair dependence exists causally, or that positive monetary expected value exists.

---

## 28. Strategy manifest contract

The `pair-v1` strategy manifest must expose every behavior-affecting strategy choice required to distinguish this implementation from another pair strategy.

At minimum, the manifest must encode the following semantics:

| Manifest semantic | Frozen value |
|---|---|
| mode | `positive_pair_deviance` |
| pair universe | `all_unordered_1_to_45` |
| pair ordering | `lexicographic_ascending` |
| history mode | `expanding` |
| null model | `uniform_6_of_45` |
| null pair probability | `1/66` |
| score | `signed_root_binomial_deviance` |
| negative policy | `zero` |
| score cap | `3.0` |
| pair weight formula | `2^(score/3)` |
| maximum pair weight | `2.0` |
| pair filtering | `none` |
| ticket combination | `additive_pair_mean` |
| sampler semantics | `weighted_anchor_pair_uniform_fill4` |
| bonus used | `false` |
| recency decay | `none` |

`min_history`, seed configuration, period size, holdout horizon, primary metric,
`evaluation_protocol_version = 1`, and prospective boundary remain ExperimentSpec fields and must
also participate in the overall experiment fingerprint according to the rules established at the
v0.4 repository/guardrail milestone. Here, `v0.4` is not the ExperimentSpec protocol identifier.

If behavior changes in a way not represented by the existing manifest, the manifest must be extended before prospective registration.

If shared evaluation semantics change, the evaluation protocol version must change.

---

## 29. Required implementation invariants

| ID | Required invariant |
|---|---|
| P1 | Pair universe contains exactly 990 unique unordered pairs. |
| P2 | Every six-number historical draw contributes exactly 15 pair observations. |
| P3 | For history length \(n\), total pair counts equal \(15n\). |
| P4 | Bonus number never enters feature computation. |
| P5 | Target round never enters its own history. |
| P6 | History is expanding from round 1 and never rolling. |
| P7 | `min_history` is exactly 330. |
| P8 | For \(n=330,c=5\), raw and final pair score are exactly zero within numerical tolerance. |
| P9 | Counts below null expectation produce final score zero. |
| P10 | Positive raw score is capped at 3. |
| P11 | Pair weights always lie in `[1, 2]`. |
| P12 | A score of zero produces pair weight 1. |
| P13 | A capped score of 3 produces pair weight 2. |
| P14 | Ticket contains exactly six unique values in `[1,45]`. |
| P15 | Anchor pair is always contained in the generated ticket. |
| P16 | The four fill numbers are sampled uniformly from the 43 non-anchor numbers. |
| P17 | All-equal pair weights imply the exact uniform distribution over all \(\binom{45}{6}\) tickets. |
| P18 | Ticket raw weight always lies in `[1,2]`. |
| P19 | Identical data, implementation, spec, and seed reproduce the identical trace. |
| P20 | Holdout history continues across the development/holdout boundary without reset. |
| P21 | Registered holdout evaluation cannot execute before all 100 rounds are available. |
| P22 | Evaluation ignores rounds after the registered 100-round horizon. |

These invariants must be verified before development performance is used to make the development pass/fail decision.

---

## 30. Change-control rule

This document defines the research identity `pair-v1`.

A code correction whose only purpose is to make an implementation conform exactly to this preregistered document is allowed before prospective registration. Any development result produced by a non-conforming implementation is invalid and must not be interpreted as `pair-v1` evidence.

A change to the hypothesis, null model, score equation, history semantics, score clipping, pair weighting, ticket weighting, sampler distribution, direction, development gate, primary metric, seed count, prospective horizon, or prospective decision rule is a behavior-affecting research change.

Such a change must create a separately named hypothesis, normally `pair-v2`.

After prospective ExperimentSpec registration, any behavior-affecting strategy or evaluation change invalidates that prospective experiment for the changed strategy and requires a new fingerprint and a new future unrevealed holdout boundary.

Non-behavioral documentation corrections may retain the `pair-v1` identity only when they provably leave all generated traces, metrics, and decision semantics unchanged.

---

## 31. Failure policy

If `pair-v1` fails its development gate, record the failure and stop `pair-v1`.

Do not rescue it by tuning parameters on rounds `1..1236`.

If a new mathematical idea is motivated by the failure, define it independently as `pair-v2` before evaluating it.

If `pair-v1` passes development but fails prospective evaluation, record the prospective failure and stop that experiment.

The revealed holdout cannot be reused as pristine confirmation data for a modified pair strategy.

Any modified strategy must use a new future holdout beginning after its own final preregistration and fingerprint commit.

---

## 32. Normative summary

`pair-v1` is exactly:

> For each target round, count every unordered number pair over all previous Lotto draws. Compare each count with the fixed IID uniform 6-of-45 null probability \(1/66\) using signed root binomial deviance. Discard negative evidence, cap positive score at 3, convert score to pair weight \(2^{s/3}\), and sample a ticket from the additive mean of its 15 pair weights using a weighted anchor pair followed by a uniform four-number fill. Pair weights are constrained to `[1,2]`. Evaluate the registered primary metric `delta_mean_matches_mean` against uniform using 100 paired seeds; the underlying raw ticket-level outcome is `matches = |T \cap Y|`. Development targets are permanently `331..1236` (\(R=906\)). Development requires the lower bound \(L_{dev}=\Delta_{dev}-1.95996398454\,SE_{dev}\) of the two-sided approximate 95% round-level uncertainty interval to exceed zero, positive median seed delta, and at least 10 positive predefined 50-round periods out of 18. This gate is a development diagnostic, not prospective confirmation. If development passes, register exactly one future `pair-v1` candidate against uniform for 100 unrevealed rounds. Prospective support requires the existing two-sided 95% round-level CI lower bound to exceed zero and both predefined 50-round holdout blocks to have positive delta.

Anything behaviorally different from the above is not `pair-v1`.
