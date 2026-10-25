# Beta and Exposure Methods

## Market beta

For aligned excess returns:

\[
r_{i,t}-r_{f,t}=\alpha_i+\beta_i(r_{m,t}-r_{f,t})+\epsilon_t
\]

For that excess-return regression, the covariance estimate uses excess returns too:

\[
\beta_i=\frac{\operatorname{Cov}(r_i-r_f,r_m-r_f)}{\operatorname{Var}(r_m-r_f)}
\]

Always report benchmark, period, frequency, observations, uncertainty, R², and residual volatility.

### Bundled calculator

`scripts/analyze.py` instead fits **raw total returns with an intercept**, because no risk-free series is supplied. Its beta is Cov(asset, benchmark)/Var(benchmark); `intercept_per_interval` is not CAPM alpha. The two regressions need not agree when the risk-free return varies.

For centered benchmark returns `dx`, residuals `e`, `Sxx = sum(dx²)` and `n` observations, the script uses `SE(beta) = sqrt(n/(n-2) * sum(dx² * e²) / Sxx²)`. This is HC1 for an intercept plus one regressor. The reported 95% interval is the large-sample normal approximation `beta ± 1.96 SE`, not an exact small-sample interval or protection against serial correlation. See the [statsmodels HC1 definition](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.HC1_se.html).

All regressions and correlations use the same common daily return intervals. Constant asset returns have undefined correlation/R²; a constant benchmark cannot identify beta. Residual standard deviation is per interval, not annualized. Scenario output omits the intercept and applies beta times a specified benchmark shock; it is a sensitivity illustration, not expected P&L.

## Multifactor model

\[
r_t-r_{f,t}=\alpha+\sum_{k=1}^{K}\beta_k f_{k,t}+\epsilon_t
\]

Use only factors with documented construction and adequate common history. Diagnose multicollinearity and unstable coefficients. A factor loading is statistical exposure, not proof of economic causality.

## Portfolio aggregation

First-order holdings-based exposure:

\[
\beta_p \approx \sum_i w_i\beta_i
\]

This approximation may fail with derivatives, leverage, changing weights, nonlinear payoffs, stale pricing, or omitted factors. Compare with realized portfolio-return regression when available.

## Rolling estimates

Use rolling windows to test stability. State:

- window length;
- minimum observations;
- rebalance/weight assumptions;
- latest value, median, range, and structural breaks.

Do not overinterpret short windows with noisy estimates.

## Upside and downside beta

Estimate conditional beta only with enough observations and a clearly defined condition, such as benchmark returns above or below zero. Report reduced sample size and selection effects.

## Correlation and concentration

Pairwise correlation:

\[
\rho_{ij}=\frac{\operatorname{Cov}(r_i,r_j)}{\sigma_i\sigma_j}
\]

Weight concentration:

\[
HHI=\sum_i w_i^2, \qquad N_{effective}=\frac{1}{HHI}
\]

For long/short or leveraged portfolios, disclose whether weights use net, gross, or absolute exposure.

## Scenario approximation

First-order factor shock:

\[
\Delta P/P \approx \sum_k \beta_k\Delta f_k
\]

This is a local linear approximation. Explicitly discuss convexity, optionality, basis risk, correlation shifts, liquidity gaps, and path dependency.

## Diagnostics checklist

- Benchmark sensitivity.
- Lookback and frequency sensitivity.
- Confidence interval or standard error.
- R² and residual distribution.
- Autocorrelation and heteroskedasticity caveat where material.
- Outlier/event sensitivity.
- Coefficient sign and economic plausibility.
- Structural breaks and regime dependence.
- Out-of-sample or holdout comparison when enough history exists.

## Interpretation limits

- High beta means high benchmark sensitivity, not necessarily high total risk.
- Low beta can coexist with severe liquidity, credit, concentration, or tail risk.
- Beta can change quickly after business-model, leverage, index, duration, or regime changes.
- Alpha/intercept from a regression is not automatically skill or investable excess return.
