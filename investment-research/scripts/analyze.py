#!/usr/bin/env python3
"""Offline single-benchmark risk estimates from documented total-return levels."""

import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class InputError(ValueError):
    """Only fixed, non-sensitive validation messages may reach CLI output."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def numeric(value):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), "finite JSON number required")
    return float(value)


def iso_date(value):
    require(isinstance(value, str), "ISO date required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InputError("analysis, observation and calendar dates must use YYYY-MM-DD") from None
    require(parsed.isoformat() == value, "YYYY-MM-DD date required")
    return value


def centered(values):
    mean = math.fsum(values) / len(values)
    return mean, [v - mean for v in values]


def correlation(x, y):
    _, dx = centered(x)
    _, dy = centered(y)
    xx, yy = math.fsum(v * v for v in dx), math.fsum(v * v for v in dy)
    if xx <= 1e-24 or yy <= 1e-24:
        return None
    return max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(dx, dy)) / math.sqrt(xx * yy)))


def fit(x, y):
    """OLS with intercept; HC1 is heteroskedasticity-, not serial-correlation-robust."""
    n = len(x)
    require(n > 2 and n == len(y), "at least three aligned returns required")
    mx, dx = centered(x)
    my, dy = centered(y)
    xx = math.fsum(v * v for v in dx)
    require(xx > 1e-24, "benchmark variance is zero or numerically negligible")
    beta = math.fsum(a * b for a, b in zip(dx, dy)) / xx
    intercept = my - beta * mx
    residual = [b - beta * a for a, b in zip(dx, dy)]
    sse = math.fsum(e * e for e in residual)
    yy = math.fsum(v * v for v in dy)
    se = math.sqrt(n / (n - 2) * math.fsum(a * a * e * e for a, e in zip(dx, residual)) / (xx * xx))
    return {"n": n, "beta": beta, "intercept_per_interval": intercept,
            "beta_se_hc1": se, "beta_ci95_asymptotic": [beta - 1.96 * se, beta + 1.96 * se],
            "r_squared": max(0.0, 1 - sse / yy) if yy > 1e-24 else None,
            "correlation": correlation(x, y), "residual_std_per_interval": math.sqrt(sse / (n - 2))}


def analyze(payload, min_observations=60, rolling_window=252):
    require(isinstance(payload, dict), "input must be an object")
    require(isinstance(min_observations, int) and min_observations >= 30,
            "min_observations must be at least 30")
    require(isinstance(rolling_window, int) and rolling_window >= min_observations,
            "rolling_window must be at least min_observations")
    as_of = iso_date(payload.get("as_of"))
    require(as_of <= datetime.now(timezone.utc).date().isoformat(), "future as_of is not allowed")
    require(payload.get("frequency") == "daily", "only daily total-return levels supported")
    currency = payload.get("currency")
    require(isinstance(currency, str) and len(currency) == 3 and currency.isalpha() and currency.isupper(),
            "explicit three-letter currency required")
    sessions = payload.get("sessions")
    require(isinstance(sessions, list) and len(sessions) >= 2, "supplied exchange sessions required")
    sessions = [iso_date(d) for d in sessions]
    require(sessions == sorted(set(sessions)) and sessions[-1] <= as_of,
            "sessions must be unique, sorted and not after as_of")
    require(isinstance(payload.get("calendar_source"), str) and payload["calendar_source"].strip(),
            "calendar_source required; its authority is not checked by this calculator")
    allowed = set(sessions)
    expected_intervals = set(zip(sessions, sessions[1:]))
    series = payload.get("series")
    require(isinstance(series, list) and len(series) >= 2, "benchmark and asset series required")
    returns, provenance, alignment = {}, {}, {}
    timing = None
    for item in series:
        require(isinstance(item, dict), "series entries must be objects")
        ident = item.get("id")
        require(isinstance(ident, str) and ident.strip() and ident not in returns, "unique nonempty series id required")
        require(item.get("currency") == currency and item.get("basis") == "total_return_index",
                "all series must share currency and total_return_index basis; no implicit FX or dividend adjustment")
        for key in ("source", "source_url", "timezone", "close_basis"):
            require(isinstance(item.get(key), str) and item[key].strip(), "source, source_url, timezone and close_basis required")
        ZoneInfo(item["timezone"])
        current_timing = (item["timezone"], item["close_basis"])
        require(timing is None or timing == current_timing, "asynchronous closes require a separately aligned dataset")
        timing = current_timing
        try:
            fetched = datetime.fromisoformat(item.get("fetched_at", ""))
        except (ValueError, TypeError):
            raise InputError("fetched_at must be an ISO timestamp with timezone") from None
        require(fetched.tzinfo is not None, "fetched_at must include timezone")
        require(fetched <= datetime.now(timezone.utc), "future fetched_at is not allowed")
        rows = item.get("observations")
        require(isinstance(rows, list) and len(rows) >= 2, "each series needs at least two observations")
        require(all(isinstance(row, dict) for row in rows), "observations must be objects")
        dates = [iso_date(row.get("date")) for row in rows]
        require(dates == sorted(set(dates)) and set(dates) <= allowed, "observation dates must be unique sorted supplied sessions")
        require(dates[-1] == sessions[-1], "series missing the last requested session; no stale-result fallback")
        require(fetched.astimezone(ZoneInfo(item["timezone"])).date().isoformat() >= dates[-1],
                "fetched_at precedes observations")
        levels = [numeric(row.get("value")) for row in rows]
        require(min(levels) > 0, "positive total-return levels required")
        # Match BOTH ends. Dropping a missing level must not turn a multi-day
        # return into a daily observation with the same ending date.
        intervals = {}
        skipped = 0
        for i in range(1, len(dates)):
            pair = (dates[i - 1], dates[i])
            if pair in expected_intervals:
                intervals[pair] = numeric(levels[i] / levels[i - 1] - 1)
            else:
                skipped += 1
        returns[ident] = intervals
        provenance[ident] = {k: item[k] for k in ("source", "source_url", "currency", "basis", "timezone", "close_basis", "fetched_at")}
        alignment[ident] = {"supplied_levels": len(rows), "valid_intervals": len(intervals),
                            "multi_session_intervals_excluded": skipped}
    benchmark = payload.get("benchmark")
    require(isinstance(benchmark, str) and benchmark in returns, "benchmark id must identify an input series")
    common = sorted(set.intersection(*(set(r) for r in returns.values())))
    require(len(common) >= min_observations, "insufficient common return intervals")
    values = {key: [r[pair] for pair in common] for key, r in returns.items()}
    for key in returns:
        alignment[key]["excluded_from_common"] = len(returns[key]) - len(common)
    x = values[benchmark]
    estimates = {key: fit(x, y) for key, y in values.items() if key != benchmark}
    weights = payload.get("weights")
    portfolio = None
    if weights is not None:
        require(isinstance(weights, dict) and weights and set(weights) <= set(values), "weights must name supplied series")
        weights = {key: numeric(value) for key, value in weights.items()}
        require(all(w >= 0 for w in weights.values()) and abs(math.fsum(weights.values()) - 1) <= 1e-6,
                "long-only weights must sum to one; represent cash explicitly, no normalization")
        weight_date = iso_date(payload.get("weights_as_of"))
        require(weight_date <= as_of, "weights_as_of cannot be after analysis date")
        portfolio_returns = [math.fsum(w * values[key][i] for key, w in weights.items()) for i in range(len(common))]
        portfolio = {"assumption": "hypothetical portfolio rebalanced to fixed weights each interval, before costs",
                     "weights": weights, "weights_as_of": weight_date,
                     "hhi": math.fsum(w * w for w in weights.values()), "estimate": fit(x, portfolio_returns)}
    rolling = {}
    for key in estimates:
        points = []
        for end in range(rolling_window, len(common) + 1):
            try:
                beta = fit(x[end - rolling_window:end], values[key][end - rolling_window:end])["beta"]
                points.append({"end": common[end - 1][1], "beta": beta})
            except ValueError:
                points.append({"end": common[end - 1][1], "beta": None, "issue": "zero_benchmark_variance"})
        rolling[key] = {"window_intervals": rolling_window, "status": "computed" if points else "insufficient_history", "points": points}
    shocks = payload.get("scenario_shocks", [])
    require(isinstance(shocks, list), "scenario_shocks must be an array")
    scenarios = []
    for shock in shocks:
        require(isinstance(shock, dict) and isinstance(shock.get("name"), str) and shock["name"].strip(), "named shock required")
        change = numeric(shock.get("benchmark_return"))
        require(-1 < change < 1, "benchmark_return must be a decimal between -1 and 1")
        scenarios.append({"name": shock["name"], "benchmark_return": change,
                          "asset_approximations": {key: result["beta"] * change for key, result in estimates.items()},
                          "portfolio_approximation": portfolio["estimate"]["beta"] * change if portfolio else None})
    return {"ok": True, "schema_version": 1, "as_of": as_of, "benchmark": benchmark, "currency": currency,
            "model": "OLS raw total returns with intercept; NOT CAPM excess-return alpha",
            "frequency": "daily", "common_intervals": len(common), "start": common[0][0], "end": common[-1][1],
            "expected_intervals": len(expected_intervals), "common_coverage": len(common) / len(expected_intervals),
            "calendar_source": payload["calendar_source"], "calendar_verified": False,
            "alignment": alignment, "provenance": provenance, "estimates": estimates, "portfolio": portfolio,
            "rolling": rolling, "correlations": {a: {b: correlation(values[a], values[b]) for b in values} for a in values},
            "scenarios": scenarios,
            "warnings": ["Supplied provenance and calendar are checked structurally, not independently verified",
                         "HC1 intervals are asymptotic and not robust to serial correlation",
                         "Rolling windows count common intervals, not necessarily consecutive trading sessions",
                         "Scenario results are local linear approximations, not forecasts or loss limits",
                         "No automatic source fetch, FX conversion, account access, trades or performance validation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--min-observations", type=int, default=60)
    parser.add_argument("--rolling-window", type=int, default=252)
    args = parser.parse_args()
    try:
        result = analyze(json.loads(args.input.read_text(encoding="utf-8")), args.min_observations, args.rolling_window)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        # Validation messages are ours; never echo raw file content or filesystem paths.
        detail = str(error) if isinstance(error, InputError) else "invalid schema, unreadable input or numeric overflow"
        result = {"ok": False, "error": type(error).__name__, "reason": detail}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
