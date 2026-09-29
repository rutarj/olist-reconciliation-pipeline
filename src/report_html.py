"""reports/dashboard.html: one self-contained interactive page (Plotly, no server, works offline).

Colors follow a validated palette (colorblind-checked): one hue for single-series charts,
blue/orange for actual vs forecast. Light and dark mode each get their own steps.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import duckdb
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

LIGHT = {"surface": "#fcfcfb", "page": "#f9f9f7", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
         "grid": "#e1e0d9", "axis": "#c3c2b7", "s1": "#2a78d6", "s2": "#eb6834"}
DARK = {"surface": "#1a1a19", "page": "#0d0d0d", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "s1": "#3987e5", "s2": "#d95926"}
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _layout(fig: go.Figure, height: int = 340, **kw) -> go.Figure:
    """Shared look. Titles live in the HTML card (they wrap on phones), not inside the plot."""
    t = LIGHT
    fig.update_layout(
        height=height, margin={"l": 8, "r": 16, "t": 12, "b": 8},
        paper_bgcolor=t["surface"], plot_bgcolor=t["surface"],
        font={"family": FONT, "color": t["ink2"], "size": 12},
        hoverlabel={"font": {"family": FONT}},
        showlegend=kw.pop("showlegend", False),
        legend={"orientation": "h", "y": -0.12, "yanchor": "top", "x": 0, "title": None},
        bargap=0.35, **kw,
    )
    fig.update_xaxes(gridcolor=t["grid"], linecolor=t["axis"], zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=t["grid"], linecolor=t["axis"], zeroline=False, automargin=True)
    return fig


def _hbar(labels, values, value_fmt, hover_extra=None, height=None, headroom=1.35) -> go.Figure:
    text = [value_fmt(v) for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", text=text, textposition="outside", cliponaxis=False, constraintext="none",
        marker={"color": LIGHT["s1"], "cornerradius": 4}, customdata=hover_extra or text,
        hovertemplate="%{y}<br>%{customdata}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    # headroom so the value label at the end of the longest bar is never clipped
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, max(values) * headroom if values else 1])
    return _layout(fig, height or max(200, 34 * len(labels) + 30))


def build_dashboard(con: duckdb.DuckDBPyConnection, metrics: dict, path: Path) -> None:
    rec, dq, fc = metrics["reconciliation"], metrics["data_quality"], metrics["forecast"]
    dlv, reviews = metrics["kpis"]["delivery"], metrics["kpis"]["reviews_by_match"]
    figs: list[tuple[str, str, go.Figure, str]] = []  # id, title, figure, note

    cats = rec["categories"]
    figs.append(("gap_brl", "Unmatched money by bucket (absolute gap, R$)",
                 _hbar([c["gap_category"].replace("_", " ") for c in cats], [c["abs_gap_brl"] for c in cats], _brl,
                       [f"{c['orders']:,} orders · {c['share_of_unmatched_gap_pct']}% of gap · severity {c['severity']}"
                        for c in cats], headroom=1.7),
                 "Orders paid with no items recorded dominate the money. Everything else is small and explained."))
    by_orders = sorted(cats, key=lambda c: -c["orders"])
    figs.append(("gap_orders", "Unmatched orders by bucket",
                 _hbar([c["gap_category"].replace("_", " ") for c in by_orders], [c["orders"] for c in by_orders],
                       lambda v: f"{v:,}"),
                 f"{rec['orders_unexplained']} orders are left unexplained after the evidence-based rules."))

    used = [s for s in fc["series"] if s.get("used", True)]
    monthly = {m["month"]: m for m in metrics["kpis"]["monthly"]}
    months = [s["month"] for s in used if s["month"] in monthly]
    fig = go.Figure(go.Scatter(
        x=months, y=[monthly[m]["match_rate_pct"] for m in months], mode="lines+markers",
        line={"color": LIGHT["s1"], "width": 2}, marker={"size": 8},
        customdata=[[monthly[m]["unmatched"], monthly[m]["orders"]] for m in months],
        hovertemplate="%{x}<br>match rate %{y:.2f}%<br>%{customdata[0]:,} of %{customdata[1]:,} orders unmatched<extra></extra>"))
    fig.update_yaxes(ticksuffix="%")
    figs.append(("match_rate", "Monthly match rate (paid = sold within R$ 0,01)", _layout(fig),
                 "Complete months only. Months at the edges of the dataset are excluded."))

    if not fc.get("skipped"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[s["month"] for s in used], y=[s["orders"] for s in used], name="Actual orders",
                                 mode="lines+markers", line={"color": LIGHT["s1"], "width": 2}, marker={"size": 8},
                                 hovertemplate="%{x}<br>actual %{y:,}<extra></extra>"))
        hold = [h for h in fc["holdout"] if h["model"] == fc["winner"]]
        fig.add_trace(go.Scatter(x=[h["month"] for h in hold] + [f["month"] for f in fc["forecast"]],
                                 y=[h["predicted"] for h in hold] + [f["forecast_orders"] for f in fc["forecast"]],
                                 name=f"{fc['winner'].replace('_', ' ')} (holdout + next 3 months)",
                                 mode="lines+markers", line={"color": LIGHT["s2"], "width": 2, "dash": "dot"},
                                 marker={"size": 8}, hovertemplate="%{x}<br>predicted %{y:,}<extra></extra>"))
        verdict = ("The naive baseline won, so it is the forecast." if fc["baseline_wins"]
                   else "A model beat the naive baselines.")
        scores = " · ".join(f"{s['model'].replace('_', ' ')} {s['holdout_mape_pct']}%" for s in fc["scores"]
                            if s["holdout_mape_pct"] is not None)
        figs.append(("forecast", "Monthly orders: actual vs forecast", _layout(fig, 380, showlegend=True),
                     f"Holdout MAPE: {scores}. {verdict}"))

    ints = rec["interest"]["by_installments"]
    fig = go.Figure(go.Bar(x=[str(i["max_installments"]) for i in ints], y=[i["median_gap_pct"] for i in ints],
                           marker={"color": LIGHT["s1"], "cornerradius": 4},
                           customdata=[i["orders"] for i in ints],
                           hovertemplate="%{x} installments<br>median overpayment %{y:.2f}%<br>%{customdata} orders<extra></extra>"))
    fig.update_yaxes(ticksuffix="%")
    fig.update_xaxes(title="installments", type="category")
    figs.append(("interest", "Evidence: card overpayment grows with installments (median % paid over sold value)",
                 _layout(fig),
                 f"{rec['interest']['on_shared_ratio_pct']}% of these orders sit on a paid/sold ratio shared by 3+ orders: a rate table, not noise."))

    st = rec["top_states"][:10]
    figs.append(("states", "Top 10 customer states by unmatched orders",
                 _hbar([f"{s['state_code']} · {s['state_name']}" for s in st], [s["unmatched"] for s in st],
                       lambda v: f"{v:,}",
                                 [f"{s['unmatched_rate_pct']}% of {s['orders']:,} orders · {_brl(s['abs_gap_brl'])}" for s in st]),
                 "Volume follows population. Hover for the unmatched rate, which is flat across big states."))

    exc = metrics["exceptions"]["by_check"]
    figs.append(("exceptions", "Exceptions by check (severity in brackets)",
                 _hbar([f"{e['check_name']} ({e['severity']})" for e in exc], [e["exceptions"] for e in exc],
                       lambda v: f"{v:,}",
                                     [f"{e['source']} · {e['table_name']} · {e['exceptions']:,}" for e in exc]),
                 "Rows are never deleted. Each failing row is logged with a reason and a severity."))

    top = con.execute("""
        select order_id, order_status, gap_category, severity, expected_total, paid_total, gap
        from fact_reconciliation where not is_matched order by abs_gap desc limit 15
    """).fetchall()
    rows = "".join(
        f"<tr><td class='mono'>{html.escape(o[:12])}…</td><td>{html.escape(s or '')}</td><td>{html.escape(c)}</td>"
        f"<td>{html.escape(sev)}</td><td class='num'>{'' if e is None else _brl(float(e))}</td>"
        f"<td class='num'>{'' if p is None else _brl(float(p))}</td><td class='num'>{_brl(float(g))}</td></tr>"
        for o, s, c, sev, e, p, g in top)

    tiles = [
        ("Match rate", f"{rec['match_rate_pct']:.2f}%", f"{rec['orders_matched']:,} of {rec['orders_total']:,} orders"),
        ("Unmatched orders", f"{rec['orders_unmatched']:,}", f"{rec['orders_value_mismatch']:,} value mismatches, rest missing a side"),
        ("Absolute gap", _brl(rec["abs_gap_brl"]), f"{rec['abs_gap_pct_of_paid']}% of {_brl(rec['paid_brl'])} paid"),
        ("Paid, no items", _brl(rec["missing_items"]["paid_brl"]), f"{rec['missing_items']['orders']:,} orders, {rec['missing_items']['canceled_or_unavailable_pct']}% canceled/unavailable"),
        ("Unexplained", f"{rec['orders_unexplained']:,} orders", f"{_brl(rec['unexplained_abs_gap_brl'])} for manual review"),
        ("Data quality exceptions", f"{dq['exceptions']:,}", f"{dq['checks_run']} checks · {dq['pct_rows_clean']}% of rows clean"),
        ("On-time delivery", f"{dlv['on_time_rate_pct']:.2f}%", f"late orders avg {dlv['avg_review_late']:.2f}★ vs {dlv['avg_review_on_time']:.2f}★ on time"),
        ("Review score", f"{reviews['unmatched']['avg_review_score']:.2f}★ vs {reviews['matched']['avg_review_score']:.2f}★",
         "unmatched vs matched orders"),
    ]
    tiles_html = "".join(f"<div class='tile'><div class='label'>{html.escape(a)}</div><div class='value'>{html.escape(b)}</div>"
                         f"<div class='sub'>{html.escape(c)}</div></div>" for a, b, c in tiles)
    cfg = {"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["select2d", "lasso2d"]}
    charts_html = "".join(
        f"<section class='card{' wide' if i == 'exceptions' else ''}'><h2>{html.escape(t)}</h2>"
        f"{pio.to_html(f, include_plotlyjs=False, full_html=False, div_id=i, config=cfg)}"
        f"<p class='note'>{html.escape(n)}</p></section>" for i, t, f, n in figs)

    page = TEMPLATE.format(
        plotly=get_plotlyjs(), light=json.dumps(LIGHT), dark=json.dumps(DARK),
        first=metrics["dataset"]["first_purchase_date"], last=metrics["dataset"]["last_purchase_date"],
        generated=metrics["generated_at"], tiles=tiles_html, charts=charts_html, rows=rows,
        **{f"L_{k}": v for k, v in LIGHT.items()}, **{f"D_{k}": v for k, v in DARK.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist Reconciliation Dashboard</title>
<style>
:root {{ --page:{L_page}; --surface:{L_surface}; --ink:{L_ink}; --ink2:{L_ink2}; --muted:{L_muted}; --grid:{L_grid};
        --ring: rgba(11,11,11,0.10); color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --page:{D_page}; --surface:{D_surface}; --ink:{D_ink};
        --ink2:{D_ink2}; --muted:{D_muted}; --grid:{D_grid}; --ring: rgba(255,255,255,0.10); color-scheme: dark; }} }}
:root[data-theme="dark"] {{ --page:{D_page}; --surface:{D_surface}; --ink:{D_ink}; --ink2:{D_ink2}; --muted:{D_muted};
        --grid:{D_grid}; --ring: rgba(255,255,255,0.10); color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font-family:{font}; line-height:1.45; }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:24px; margin:0 0 4px; }}
.lede {{ color:var(--ink2); margin:0 0 20px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:12px; margin-bottom:16px; }}
.tile, .card {{ background:var(--surface); border:1px solid var(--ring); border-radius:10px; padding:14px 16px; }}
.tile .label {{ color:var(--ink2); font-size:13px; }}
.tile .value {{ font-size:26px; font-weight:650; margin:2px 0; }}
.tile .sub {{ color:var(--muted); font-size:12.5px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(460px, 1fr)); gap:12px; }}
.card {{ min-width:0; }}
.card h2 {{ font-size:15px; font-weight:600; margin:0 0 6px; }}
.wide {{ grid-column:1 / -1; }}
.note {{ color:var(--ink2); font-size:13px; margin:6px 2px 0; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:6px 8px; border-bottom:1px solid var(--grid); text-align:left; }}
th {{ color:var(--ink2); font-weight:600; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.mono {{ font-family:ui-monospace, Menlo, monospace; }}
.table-wrap {{ overflow-x:auto; }}
footer {{ color:var(--muted); font-size:12.5px; margin-top:24px; }}
a {{ color:inherit; }}
@media (max-width:520px) {{ .grid {{ grid-template-columns:1fr; }} .tile .value {{ font-size:22px; }} }}
</style>
<script>{plotly}</script>
</head><body><main>
<h1>Olist reconciliation, data quality &amp; KPIs</h1>
<p class="lede">Two systems, one question: does what was sold (order items) equal what was paid (payments)?
Orders purchased {first} to {last}. All money in Brazilian real (R$, BRL). Generated {generated}.</p>
<div class="tiles">{tiles}</div>
<div class="grid">{charts}</div>
<section class="card" style="margin-top:12px"><h2>15 largest gaps</h2>
<div class="table-wrap"><table><thead><tr><th>order</th><th>status</th><th>bucket</th><th>severity</th>
<th class="num">sold</th><th class="num">paid</th><th class="num">gap</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<footer>Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle), licensed CC BY-NC-SA 4.0. Built by run_pipeline.py;
every number comes from reports/metrics.json.</footer>
</main>
<script>
const THEMES = {{ light: {light}, dark: {dark} }};
function currentTheme() {{
  const forced = document.documentElement.getAttribute("data-theme");
  if (forced) return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}}
function applyTheme() {{
  const t = THEMES[currentTheme()];
  document.querySelectorAll(".js-plotly-plot").forEach(gd => {{
    const colors = gd.data.map((tr, i) => i === 0 ? t.s1 : t.s2);
    Plotly.restyle(gd, {{"marker.color": colors, "line.color": colors}});
    Plotly.relayout(gd, {{paper_bgcolor: t.surface, plot_bgcolor: t.surface, "font.color": t.ink2,
      "xaxis.gridcolor": t.grid, "yaxis.gridcolor": t.grid, "xaxis.linecolor": t.axis, "yaxis.linecolor": t.axis,
      }});
  }});
}}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
new MutationObserver(applyTheme).observe(document.documentElement, {{attributes: true, attributeFilter: ["data-theme"]}});
window.addEventListener("load", applyTheme);
</script>
</body></html>
""".replace("{font}", FONT.replace('"', "'"))
