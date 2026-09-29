"""Monthly order volume forecast, judged against naive baselines on a holdout.

Steps
1. Monthly order counts by purchase month.
2. Keep the continuous run of "complete" months. The data starts with a few test-like
   months in 2016 and ends with near-empty months in Sep/Oct 2018 (collection cut-off).
   A month is complete if it has at least 10% of the median monthly volume.
3. Hold out the last 3 complete months. Fit every candidate on the months before.
4. Score with MAPE (mean absolute percentage error) on the holdout.
5. Refit the winner on all complete months and forecast the next 3 months.
   If a naive baseline wins, we say so and use it. A fancy model that loses to
   "same as last month" is not worth shipping.
"""
from __future__ import annotations

import logging
import warnings

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

log = logging.getLogger(__name__)

HORIZON = 3
MIN_SHARE_OF_MEDIAN = 0.10
MIN_TRAIN_MONTHS = 12


def monthly_orders(con: duckdb.DuckDBPyConnection) -> pd.Series:
    df = con.execute("""
        select d.month_start, count(*) as orders
        from fact_orders f join dim_date d on d.date_key = f.purchase_date_key
        group by 1 order by 1
    """).df()
    s = df.set_index(pd.to_datetime(df["month_start"]))["orders"].astype(float)
    return s.asfreq("MS", fill_value=0.0)


def complete_window(s: pd.Series) -> pd.Series:
    ok = s >= MIN_SHARE_OF_MEDIAN * s.median()
    # longest run of consecutive complete months
    run_id = (~ok).cumsum()
    runs = s[ok].groupby(run_id[ok])
    best = max(runs.groups, key=lambda k: len(runs.groups[k]))
    return s[runs.groups[best]]


def mape(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs((actual - pred) / actual)) * 100)


# Candidate models: each takes the training series and returns HORIZON predictions.
def naive_last(train: pd.Series) -> np.ndarray:
    return np.repeat(train.iloc[-1], HORIZON)


def seasonal_naive(train: pd.Series) -> np.ndarray:
    if len(train) < 12:
        return np.full(HORIZON, np.nan)
    return train.iloc[-12:-12 + HORIZON].to_numpy() if HORIZON < 12 else train.iloc[-12:].to_numpy()


def moving_average_3(train: pd.Series) -> np.ndarray:
    return np.repeat(train.iloc[-3:].mean(), HORIZON)


def holt_damped(train: pd.Series) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(train.to_numpy(), trend="add", damped_trend=True,
                                   initialization_method="estimated").fit()
    return fit.forecast(HORIZON)


MODELS = {
    "naive_last_value": ("baseline", naive_last),
    "seasonal_naive_12m": ("baseline", seasonal_naive),
    "moving_average_3m": ("model", moving_average_3),
    "holt_damped_trend": ("model", holt_damped),
}


def run_forecast(con: duckdb.DuckDBPyConnection) -> dict:
    full = monthly_orders(con)
    series = [{"month": m.strftime("%Y-%m"), "orders": int(v)} for m, v in full.items()]
    s = complete_window(full) if len(full) else full
    if len(s) < MIN_TRAIN_MONTHS + HORIZON or (s.iloc[-HORIZON:] == 0).any():
        log.info("  forecast skipped: only %d complete months", len(s))
        return {"skipped": True, "reason": f"only {len(s)} complete months", "series": series}
    train, test = s.iloc[:-HORIZON], s.iloc[-HORIZON:]

    scores, holdout_rows = [], []
    for name, (kind, fn) in MODELS.items():
        try:
            pred = np.asarray(fn(train), dtype=float)
        except Exception as exc:  # a model that cannot fit is scored as missing, not fatal
            log.warning("  %s failed: %s", name, exc)
            pred = np.full(HORIZON, np.nan)
        score = mape(test.to_numpy(), pred) if not np.isnan(pred).any() else None
        scores.append({"model": name, "kind": kind, "holdout_mape_pct": None if score is None else round(score, 2)})
        for month, a, p in zip(test.index, test.to_numpy(), pred):
            holdout_rows.append({"month": month.strftime("%Y-%m"), "model": name, "actual": int(a),
                                 "predicted": None if np.isnan(p) else round(float(p), 0)})

    ranked = sorted((x for x in scores if x["holdout_mape_pct"] is not None), key=lambda x: x["holdout_mape_pct"])
    best = ranked[0]
    best_baseline = next(x for x in ranked if x["kind"] == "baseline")
    best_model = next(x for x in ranked if x["kind"] == "model")

    future_idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(1), periods=HORIZON, freq="MS")
    future = MODELS[best["model"]][1](s)
    forecast_rows = [{"month": m.strftime("%Y-%m"), "forecast_orders": int(round(float(v)))}
                     for m, v in zip(future_idx, future)]

    excluded = [m.strftime("%Y-%m") for m in full.index if m not in s.index]
    result = {
        "skipped": False,
        "series": [dict(r, used=pd.Timestamp(r["month"]) in s.index) for r in series],
        "window_start": s.index[0].strftime("%Y-%m"),
        "window_end": s.index[-1].strftime("%Y-%m"),
        "train_months": len(train),
        "holdout_months": [m.strftime("%Y-%m") for m in test.index],
        "excluded_months": excluded,
        "scores": scores,
        "holdout": holdout_rows,
        "winner": best["model"],
        "winner_kind": best["kind"],
        "winner_mape_pct": best["holdout_mape_pct"],
        "best_baseline": best_baseline["model"],
        "best_baseline_mape_pct": best_baseline["holdout_mape_pct"],
        "best_model": best_model["model"],
        "best_model_mape_pct": best_model["holdout_mape_pct"],
        "baseline_wins": best["kind"] == "baseline",
        "forecast": forecast_rows,
    }
    log.info("  holdout MAPE: %s", ", ".join(f"{x['model']}={x['holdout_mape_pct']}" for x in scores))
    log.info("  winner: %s (%s)", best["model"], best["kind"])
    return result


def forecast_table(result: dict) -> pd.DataFrame:
    """Long table for BI tools: one row per month and series (actual, each model's holdout, the forecast)."""
    rows = [{"month": s["month"], "series": "actual", "row_type": "actual", "orders": s["orders"],
             "used_in_model": s.get("used", False)} for s in result["series"]]
    if not result.get("skipped"):
        rows += [{"month": h["month"], "series": h["model"], "row_type": "holdout", "orders": h["predicted"],
                  "used_in_model": True} for h in result["holdout"]]
        rows += [{"month": f["month"], "series": result["winner"], "row_type": "forecast",
                  "orders": f["forecast_orders"], "used_in_model": False} for f in result["forecast"]]
    df = pd.DataFrame(rows)
    df["orders"] = df["orders"].round().astype("Int64")
    df["month_start"] = pd.to_datetime(df["month"] + "-01")
    return df
