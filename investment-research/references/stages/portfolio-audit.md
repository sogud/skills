# Stage: Portfolio Audit

## Purpose

Synthesize regime, exposure, correlation, and stress artifacts into an auditable systematic-risk report.

This stage diagnoses risk. It does not prescribe trades or access an account.

## Inputs

Use the applicable artifacts:

- `beta-brief.md`
- `market-regime.md`
- `factor-exposure.md`
- `correlation-risk.md`
- `scenario-stress.md`

Read `templates/beta-report.html` only if HTML is explicitly requested. Otherwise synthesize into the canonical Markdown report; stage files need not be separate artifacts.

## Process

1. Re-run the Beta Gate against current inputs and timestamps.
2. Explain what the benchmark represents and what it misses.
3. Identify dominant systematic exposures and whether they are stable.
4. Identify concentration hidden by names, sectors, or nominal position count.
5. Compare current regime exposure with historical and hypothetical stresses.
6. Separate measured risk from unmeasured liquidity, credit, operational, path, and tail risks.
7. List monitoring indicators and conditions that would invalidate current estimates.
8. Convert analytical findings into research questions, not trading instructions.

## Required report sections

1. Plain-language conclusion.
2. Scope, benchmark, currency, and data cutoff.
3. Beta Gate status.
4. Market regime dashboard.
5. Static and rolling beta/factor exposure.
6. Correlation and concentration map.
7. Scenario stress table.
8. Dominant risks and diversification limits.
9. Observed Data / Estimate / Assumption / Data Gap table.
10. Monitoring and invalidation conditions.
11. Methodology and limitations.
12. Sources and research-only disclaimer.

## Visual standard

Use compact tables and no chart wall. Useful visuals include:

- rolling beta line;
- factor-exposure bar chart;
- compact correlation heatmap;
- scenario contribution bar chart.

Every figure must state data window, source, method, and units. Prefer ECharts SVG rendering with readable fallback text.

## Output

Produce one canonical Markdown report. HTML is an optional requested rendering, not another research workflow. If core input checks fail, state the missing data and withhold dependent estimates; independently supported findings may still be reported with their limits.

## Final verdict

Use one label:

- **COMPLETE:** core inputs and diagnostics support the conclusions.
- **LIMITED:** useful but material Data Gaps constrain interpretation.
- **BLOCKED:** core data or comparability is invalid.
