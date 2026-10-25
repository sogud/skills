# Beta Research Data Contract

## Minimum inputs by research object

| Object | Required | Optional |
|---|---|---|
| Market | Scope, analysis date, benchmark, regime indicators | Cross-asset and factor data |
| Asset | Adjusted asset and benchmark return history | Risk-free and factor returns |
| Portfolio | Holdings plus weights, or portfolio return history; benchmark | Holdings histories, factors, classifications |
| Stress | Exposure estimates or aligned histories; explicit shocks | Nonlinear pricing models |

## Return-series rules

- Prefer adjusted total-return data including splits and distributions.
- Record source, symbol/identifier, timezone, currency, frequency, start/end date, and access time.
- Align return intervals by both start and end date, not just their ending date. A missing daily level must not create a multi-day return labeled as daily.
- Do not forward-fill returns across non-trading or stale-price periods without explicit justification.
- Explain missing-value treatment and dropped observations.
- Convert currency consistently or disclose that local-currency and investor-currency results differ.
- Use return series, not price levels, for beta and correlation.
- Flag survivorship, backfill, stale pricing, delisting, and benchmark-composition bias.

## Portfolio rules

- Weights must state the effective date and should reconcile to approximately 100%; explain cash, leverage, shorts, derivatives, and residuals.
- For derivatives, notional weight is not enough when delta, duration, convexity, or nonlinear exposure is material.
- Distinguish holdings-based exposure from realized return-based exposure.
- Never silently retrieve holdings from a brokerage account.

## Factor rules

For every factor, record:

- economic meaning;
- exact construction/provider;
- return type and currency;
- frequency and coverage;
- whether it is investable, academic, macro, or custom;
- known overlap with other factors.

Do not combine incompatible factor definitions as though they were the same series.

## Data-quality statuses

- **Ready:** sufficient, aligned, current, and documented.
- **Limited:** usable with explicit constraints.
- **Blocked:** missing core series, invalid alignment, unknown provenance, or incomparable definitions.

## Offline calculator contract

Run from this skills repository's root (otherwise use the script's absolute path):

```bash
python3 investment-research/scripts/analyze.py --input /path/to/beta-input.json
```

No fetch, account read, installation or file write is performed. Exit 0 means the input passed structural checks and the calculation completed; exit 2 returns a structured error. This does not verify provider accuracy, exchange calendars, investment suitability or forecasting skill.

Input is a JSON object with:

| Field | Requirement |
|---|---|
| `as_of` | Analysis cutoff `YYYY-MM-DD`, not in the future |
| `benchmark` | ID of one supplied series |
| `currency`, `frequency` | Explicit common currency such as `USD`; frequency must be `daily` |
| `sessions`, `calendar_source` | Sorted unique requested trading dates and original calendar source; checked structurally, not independently authenticated |
| `series` | Benchmark plus one or more assets using the fields below |
| `weights`, `weights_as_of` | Optional explicit long-only weights keyed by supplied series IDs, sum to 1, with effective date no later than `as_of`. Never silently normalize or omit cash |
| `scenario_shocks` | Optional objects with `name` and decimal `benchmark_return`, e.g. `-0.10` |

Each series requires `id`, `source`, `source_url`, `currency`, `basis: "total_return_index"`, IANA `timezone`, `close_basis`, timezone-aware `fetched_at`, and `observations: [{"date": "YYYY-MM-DD", "value": 100.0}, ...]`. The values are positive total-return index levels, not percentage returns or raw closes. Source values must come from actual data; never populate a missing history with model-generated numbers.

- Preserve raw provider fields and the documented split/distribution adjustment when constructing this input. The existing A-share `history` and fund `nav` outputs are **not automatically** total-return indices. A fund unit NAV omitting distributions, gold spot price, futures close, and equity adjusted close cannot silently be mixed as equivalent investor returns.
- `close_basis` identifies the actual observation convention, e.g. `XNYS_regular_close`. All series must share it and timezone; copying the label onto asynchronous NAVs does not make them aligned. Mixed markets require a separately justified common-observation dataset; this calculator does not perform that transformation.
- Dates must belong to the supplied calendar and include its final requested session. Missing intermediate levels exclude both affected daily intervals; no fill or multi-day return substitution. Output reports common coverage and per-series exclusions.
- Default minimum is 60 common intervals, configurable with `--min-observations` but never below 30. Default rolling window is 252 common intervals (`--rolling-window`, at least the chosen minimum). Short rolling history is explicitly unavailable; it does not invalidate an otherwise sufficient static estimate. These are practical conventions, not statistical power guarantees.
- Every asset and the correlation matrix use the same intersection. Adding a short-history asset can reduce the entire sample; inspect actual dates and exclusions rather than presenting the requested range as the measured range.
- `weights` describes a hypothetical portfolio rebalanced to those fixed weights each interval, before costs; it is not a historical account return series. Cash needs its own correctly defined series. Shorts, leverage and nonlinear products require another explicitly justified model, not fake normalized weights.
- A historical `as_of` is valid for research, but cannot be described as current. Check source freshness again when using its result in today's decisions.

Output includes raw-total-return OLS estimates, HC1 uncertainty, R², residual variability, rolling estimates, common-sample correlations, optional portfolio/scenario results, provenance and limitations. Read `beta-methods.md` before interpreting it. Use synthetic inputs to check arithmetic and failure handling; they do not verify live data availability or returns.
