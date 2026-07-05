"""
Strategy 1 — TradingView Lightweight Charts Visualization
=========================================================
Produces an interactive HTML chart using TradingView's lightweight-charts (v4)
library — the same rendering engine behind TradingView.com.

Layout
------
+------------------------------------------+-------------------+
|  Candlestick + Volume overlay            |  Volume Profile   |
|  + Key-level price lines                 |  (horizontal bars)|
|  + Buy / Sell markers                    |                   |
+------------------------------------------+  VP Stats         |
|  Bar Delta  (histogram)                  +-------------------+
+------------------------------------------+  Strategy Info    |
|  Cumulative Delta  (area)                |  Key Levels       |
|                                          |  Signals / Rules  |
+------------------------------------------+-------------------+

Usage
-----
  python -m order_flow_scalper.chart                 # 100 M1 bars, opens browser
  python -m order_flow_scalper.chart --bars 60        # last 60 M1 bars
  python -m order_flow_scalper.chart --footprint      # also generate footprint chart
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

import config
from mt5_connector import MT5Connector
from data_puller import DataPuller
from volume_profile import build_volume_profile, VolumeProfile
from key_levels import KeyLevelBuilder, KeyLevels
from footprint import FootprintBuilder, FootprintBar
from delta import DeltaEngine, DeltaBar
from signals import SignalDetector, Signal, SignalType

log = logging.getLogger(__name__)

# --- colour palette (TradingView dark) --------
C_BG          = "#131722"
C_GRID        = "#1e222d"
C_BORDER      = "#2a2e39"
C_TEXT        = "#d1d4dc"
C_TEXT_DIM    = "#787b86"
C_GREEN       = "#26a69a"
C_RED         = "#ef5350"
C_VPOC        = "#e040fb"
C_VAH         = "#42a5f5"
C_VAL         = "#42a5f5"
C_PDH         = "#ffa726"
C_PDL         = "#ffa726"
C_PDC         = "#ffcc80"
C_OR          = "#4caf50"
C_OVERNIGHT   = "#78909c"
C_WKLY_VWAP   = "#00e5ff"
C_MTHLY_VWAP  = "#ffeb3b"
C_SIGNAL_BUY  = "#00e676"
C_SIGNAL_SELL = "#ff1744"
C_CUM_DELTA   = "#7c4dff"


# ==============================================================
#  Timestamp helper
# ==============================================================
def _ts(t) -> int:
    """Convert any timestamp to Unix seconds (UTC)."""
    if isinstance(t, (int, np.integer)):
        return int(t)
    return int(pd.Timestamp(t).value // 10**9)


# ==============================================================
#  Main entry -- pull data & build chart
# ==============================================================
def build_strategy_chart(
    bar_count: int = 100,
    output_html: str = "strategy_chart.html",
    auto_open: bool = True,
) -> Optional[str]:
    """Pull live data from MT5, compute all components, render TradingView chart."""

    conn = MT5Connector()
    conn.connect()
    try:
        puller = DataPuller(config.SYMBOL)
        tick_size = conn.spec.point if conn.spec else 0.01

        bar_data = puller.pull_bars(config.TIMEFRAME_PRIMARY, count=bar_count)
        if bar_data is None or bar_data.df.empty:
            log.error("No M1 bar data -- cannot build chart")
            return None
        bars = bar_data.df.copy()

        tick_data = puller.pull_ticks_session()
        ticks = tick_data.df if tick_data else pd.DataFrame()

        vp = build_volume_profile(ticks, tick_size) if not ticks.empty else None

        kl_builder = KeyLevelBuilder(puller, tick_size)
        kl = kl_builder.build(vp)

        fp_builder = FootprintBuilder(tick_size)
        fp_bars: List[FootprintBar] = []
        if not ticks.empty and not bars.empty:
            fp_bars = fp_builder.build_footprint(ticks, bars)

        delta_engine = DeltaEngine()
        delta_bars: List[DeltaBar] = []
        if fp_bars:
            delta_bars = delta_engine.compute_from_footprint(fp_bars)

        detector = SignalDetector(fp_builder, delta_engine, tick_size)
        current_price = float(bars["close"].iloc[-1])
        signals: List[Signal] = []
        if fp_bars and kl:
            signals = detector.scan_all(
                fp_bars=fp_bars,
                key_levels=kl,
                current_price=current_price,
                tick_df=ticks if not ticks.empty else None,
            )
    finally:
        conn.disconnect()

    # -- Serialize all data to JSON ----------------
    candle_j   = _serialize_candles(bars)
    volume_j   = _serialize_volume(bars, fp_bars)
    delta_j    = _serialize_delta(delta_bars)
    cumdelta_j = _serialize_cum_delta(delta_bars)
    levels_j   = _serialize_key_levels(kl)
    markers_j  = _serialize_markers(signals)
    vp_j       = _serialize_vp(vp)
    expl_html  = _build_explanation(kl, vp, signals, delta_bars, fp_bars)

    html = _generate_html(
        candle_j, volume_j, delta_j, cumdelta_j,
        levels_j, markers_j, vp_j, expl_html,
    )

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    if auto_open:
        import webbrowser
        webbrowser.open(f"file:///{os.path.abspath(out_path)}")

    log.info("TradingView chart saved -> %s", out_path)
    return out_path


# ==============================================================
#  Data -> JSON serializers
# ==============================================================
def _serialize_candles(bars: pd.DataFrame) -> str:
    seen, records = set(), []
    for _, r in bars.iterrows():
        t = int(r["time"])
        if t in seen:
            continue
        seen.add(t)
        records.append({
            "time": t,
            "open":  round(float(r["open"]), 2),
            "high":  round(float(r["high"]), 2),
            "low":   round(float(r["low"]), 2),
            "close": round(float(r["close"]), 2),
        })
    records.sort(key=lambda x: x["time"])
    return json.dumps(records)


def _serialize_volume(bars: pd.DataFrame, fp_bars: List[FootprintBar]) -> str:
    seen, records = set(), []
    if fp_bars:
        for fp in fp_bars:
            t = _ts(fp.bar_time)
            if t in seen:
                continue
            seen.add(t)
            total = fp.total_buy_vol + fp.total_sell_vol
            color = C_GREEN if fp.total_buy_vol >= fp.total_sell_vol else C_RED
            records.append({"time": t, "value": round(total, 2), "color": color + "80"})
    else:
        for _, r in bars.iterrows():
            t = int(r["time"])
            if t in seen:
                continue
            seen.add(t)
            color = C_GREEN if r["close"] >= r["open"] else C_RED
            records.append({"time": t, "value": float(r["tick_volume"]), "color": color + "80"})
    records.sort(key=lambda x: x["time"])
    return json.dumps(records)


def _serialize_delta(delta_bars: List[DeltaBar]) -> str:
    seen, records = set(), []
    for db in delta_bars:
        t = _ts(db.bar_time)
        if t in seen:
            continue
        seen.add(t)
        records.append({
            "time": t,
            "value": round(db.delta, 2),
            "color": C_GREEN if db.delta >= 0 else C_RED,
        })
    records.sort(key=lambda x: x["time"])
    return json.dumps(records)


def _serialize_cum_delta(delta_bars: List[DeltaBar]) -> str:
    seen, records = set(), []
    for db in delta_bars:
        t = _ts(db.bar_time)
        if t in seen:
            continue
        seen.add(t)
        records.append({"time": t, "value": round(db.cum_delta, 2)})
    records.sort(key=lambda x: x["time"])
    return json.dumps(records)


def _serialize_key_levels(kl: Optional[KeyLevels]) -> str:
    if not kl:
        return "[]"
    # lineStyle: 0=Solid 1=Dotted 2=Dashed 3=LargeDashed 4=SparseDotted
    defs = [
        (kl.prev_day_high,      "PDH",   C_PDH,        1, 2),
        (kl.prev_day_low,       "PDL",   C_PDL,        1, 2),
        (kl.prev_day_close,     "PDC",   C_PDC,        1, 1),
        (kl.vpoc,               "VPOC",  C_VPOC,       2, 0),
        (kl.vah,                "VAH",   C_VAH,        1, 3),
        (kl.val,                "VAL",   C_VAL,        1, 3),
        (kl.opening_range_high, "OR-H",  C_OR,         1, 2),
        (kl.opening_range_low,  "OR-L",  C_OR,         1, 2),
        (kl.overnight_high,     "ON-H",  C_OVERNIGHT,  1, 1),
        (kl.overnight_low,      "ON-L",  C_OVERNIGHT,  1, 1),
        (kl.weekly_vwap,        "wVWAP", C_WKLY_VWAP,  1, 0),
        (kl.monthly_vwap,       "mVWAP", C_MTHLY_VWAP, 1, 0),
    ]
    levels = []
    for val, label, color, w, style in defs:
        if val > 0:
            levels.append({
                "price": round(val, 2),
                "title": label,
                "color": color,
                "lineWidth": w,
                "lineStyle": style,
            })
    return json.dumps(levels)


def _serialize_markers(signals: List[Signal]) -> str:
    markers = []
    for s in signals:
        is_buy = s.direction == "long"
        markers.append({
            "time": _ts(s.bar_time),
            "position": "belowBar" if is_buy else "aboveBar",
            "color": C_SIGNAL_BUY if is_buy else C_SIGNAL_SELL,
            "shape": "arrowUp" if is_buy else "arrowDown",
            "text": f"{s.signal_type.value} ({s.confidence:.0%})",
        })
    markers.sort(key=lambda m: m["time"])
    return json.dumps(markers)


def _serialize_vp(vp: Optional[VolumeProfile]) -> str:
    if not vp or vp.profile_df.empty:
        return "[]"
    prof = vp.profile_df.copy()
    max_vol = prof["total_vol"].max()
    if max_vol == 0:
        return "[]"
    if len(prof) > 200:
        step = max(1, len(prof) // 200)
        prof = prof.iloc[::step].reset_index(drop=True)
    tick_h = np.median(np.diff(prof["price"].sort_values().values)) if len(prof) > 1 else 1.0
    records = []
    for _, r in prof.iterrows():
        pct = r["total_vol"] / max_vol * 100
        is_vpoc = abs(r["price"] - vp.vpoc) <= tick_h
        is_va = vp.val <= r["price"] <= vp.vah
        records.append({
            "price":   round(float(r["price"]), 2),
            "volume":  round(float(r["total_vol"]), 2),
            "pct":     round(pct, 1),
            "buyVol":  round(float(r["buy_vol"]), 2),
            "sellVol": round(float(r["sell_vol"]), 2),
            "isVpoc":  bool(is_vpoc),
            "isVa":    bool(is_va),
        })
    return json.dumps(records)


# ==============================================================
#  Explanation sidebar HTML
# ==============================================================
def _build_explanation(kl, vp, signals, delta_bars, fp_bars) -> str:
    n_signals = len(signals)
    n_buy  = sum(1 for s in signals if s.direction == "long")
    n_sell = sum(1 for s in signals if s.direction == "short")
    cum_delta = delta_bars[-1].cum_delta if delta_bars else 0
    delta_bias = "BULLISH" if cum_delta > 0 else "BEARISH" if cum_delta < 0 else "NEUTRAL"
    total_vol = sum(fp.total_buy_vol + fp.total_sell_vol for fp in fp_bars) if fp_bars else 0
    buy_ratio = (sum(fp.total_buy_vol for fp in fp_bars) / total_vol * 100) if total_vol > 0 else 50
    bias_clr = C_GREEN if delta_bias == "BULLISH" else C_RED if delta_bias == "BEARISH" else C_TEXT_DIM

    h = ""

    # -- Key Levels --
    h += '<div class="exp-section">'
    h += '<div class="exp-title">Key Levels</div>'
    if kl:
        for val, label, color, desc in [
            (kl.prev_day_high,      "PDH",   C_PDH,       "Previous Day High"),
            (kl.prev_day_low,       "PDL",   C_PDL,       "Previous Day Low"),
            (kl.prev_day_close,     "PDC",   C_PDC,       "Previous Day Close"),
            (kl.vpoc,               "VPOC",  C_VPOC,      "Volume Point of Control"),
            (kl.vah,                "VAH",   C_VAH,       "Value Area High"),
            (kl.val,                "VAL",   C_VAL,       "Value Area Low"),
            (kl.opening_range_high, "OR-H",  C_OR,        "Opening Range High"),
            (kl.opening_range_low,  "OR-L",  C_OR,        "Opening Range Low"),
            (kl.overnight_high,     "ON-H",  C_OVERNIGHT, "Overnight High"),
            (kl.overnight_low,      "ON-L",  C_OVERNIGHT, "Overnight Low"),
            (kl.weekly_vwap,        "wVWAP", C_WKLY_VWAP, "Weekly VWAP"),
            (kl.monthly_vwap,       "mVWAP", C_MTHLY_VWAP,"Monthly VWAP"),
        ]:
            if val > 0:
                h += (
                    f'<div class="exp-level">'
                    f'<span class="exp-swatch" style="background:{color}"></span>'
                    f'<span style="color:{color};font-weight:600">{label}</span> '
                    f'{val:,.2f} '
                    f'<span class="exp-dim">{desc}</span>'
                    f'</div>'
                )
    h += '</div>'

    # -- Signals --
    h += '<div class="exp-section">'
    h += f'<div class="exp-title">Signals ({n_signals})</div>'
    if n_signals:
        h += f'<div style="margin-bottom:4px">&#9650; {n_buy} buy &nbsp; &#9660; {n_sell} sell</div>'
        for s in signals[:6]:
            icon = "&#9650;" if s.direction == "long" else "&#9660;"
            clr = C_SIGNAL_BUY if s.direction == "long" else C_SIGNAL_SELL
            h += (
                f'<div style="color:{clr};font-size:11px">'
                f'{icon} {s.signal_type.value} @ {s.key_level:,.2f} ({s.confidence:.0%})</div>'
            )
    else:
        h += f'<div class="exp-dim">No signals detected</div>'
    h += '</div>'

    # -- Delta --
    h += '<div class="exp-section">'
    h += '<div class="exp-title">Delta Analysis</div>'
    h += (
        f'<div>Cum Delta: <b>{cum_delta:,.0f}</b> &rarr; '
        f'<span style="color:{bias_clr};font-weight:700">{delta_bias}</span></div>'
    )
    h += f'<div>Buy ratio: {buy_ratio:.1f}%</div>'
    h += '</div>'

    # -- Strategy Rules --
    h += '<div class="exp-section">'
    h += '<div class="exp-title">Strategy Rules</div>'
    rules = [
        "1. Price at a key level",
        "2. Order flow signal (absorption / imbalance / iceberg / exhaustion)",
        "3. Volume Profile context (near VAH / VAL / VPOC)",
        "4. Cumulative Delta confirms direction",
        "5. DOM / tape supports the trade",
        f"<b>&rarr; Need &ge; 3/5 confluences</b>",
        f"Risk: {config.RISK_PER_TRADE:.0%}/trade &nbsp;|&nbsp; R:R &ge; {config.MIN_RR_RATIO}",
        f"Scale-out: {'/'.join(str(int(s*100))+'%' for s in config.TP_SPLIT)}",
        f"TP&#8321;={config.TP1_TICKS}t &nbsp; TP&#8322;={config.TP2_TICKS}t &nbsp; TP&#8323;={config.TP3_TICKS}t &nbsp; SL={config.STOP_TICKS}t",
    ]
    for r in rules:
        h += f'<div class="exp-rule">{r}</div>'
    h += '</div>'

    # -- Trading Mode --
    h += '<div class="exp-section">'
    if config.IS_CRYPTO:
        h += '<div class="exp-title">Crypto Mode</div>'
        h += '<div class="exp-rule">24/7 trading (killzones bypassed)</div>'
    else:
        h += '<div class="exp-title">Killzones (EST)</div>'
        for kz in config.KILLZONES:
            h += f'<div class="exp-rule">{kz[0]:02d}:{kz[1]:02d} &ndash; {kz[2]:02d}:{kz[3]:02d}</div>'
        dz = config.DEAD_ZONE
        h += f'<div class="exp-rule">Dead zone: {dz[0]:02d}:{dz[1]:02d} &ndash; {dz[2]:02d}:{dz[3]:02d}</div>'
    h += '</div>'

    return h


# ==============================================================
#  HTML generation (TradingView lightweight-charts)
# ==============================================================
def _generate_html(candle_j, volume_j, delta_j, cumdelta_j,
                   levels_j, markers_j, vp_j, expl_html) -> str:
    """Build self-contained HTML powered by lightweight-charts v4."""
    html = _HTML_TEMPLATE
    for key, val in {
        "__CANDLE_DATA__":   candle_j,
        "__VOLUME_DATA__":   volume_j,
        "__DELTA_DATA__":    delta_j,
        "__CUMDELTA_DATA__": cumdelta_j,
        "__KEY_LEVELS__":    levels_j,
        "__MARKERS__":       markers_j,
        "__VP_DATA__":       vp_j,
        "__EXPLANATION__":   expl_html,
        "__SYMBOL__":        config.SYMBOL,
        "__C_BG__":          C_BG,
        "__C_GRID__":        C_GRID,
        "__C_BORDER__":      C_BORDER,
        "__C_TEXT__":         C_TEXT,
        "__C_TEXT_DIM__":     C_TEXT_DIM,
        "__C_GREEN__":       C_GREEN,
        "__C_RED__":         C_RED,
        "__C_VPOC__":        C_VPOC,
        "__C_VAH__":         C_VAH,
        "__C_CUM_DELTA__":   C_CUM_DELTA,
    }.items():
        html = html.replace(key, val)
    return html


# ---------------------------------------------------------------
#  HTML + JS template  (uses __PLACEHOLDER__ tokens)
# ---------------------------------------------------------------
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Order Flow Scalper | __SYMBOL__ | TradingView</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{
  background:__C_BG__;color:__C_TEXT__;
  font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
}

/* -- header ---------------------- */
.header{
  height:38px;display:flex;align-items:center;padding:0 16px;
  background:#1c2030;border-bottom:1px solid __C_BORDER__;
  font-size:13px;gap:16px;
}
.header .sym{font-weight:700;font-size:15px;letter-spacing:.5px}
.header .tf{color:__C_TEXT_DIM__}
.header .badge{
  font-size:10px;padding:2px 8px;border-radius:3px;
  background:rgba(38,166,154,.15);color:__C_GREEN__;font-weight:600;
}

/* -- layout ---------------------- */
.container{display:flex;height:calc(100vh - 38px)}
.charts-col{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
.chart-pane{position:relative;overflow:hidden}
.pane-label{
  position:absolute;top:6px;left:12px;z-index:10;
  font-size:11px;color:__C_TEXT_DIM__;pointer-events:none;
  background:rgba(19,23,34,.7);padding:2px 8px;border-radius:3px;
}
#main-chart{flex:5}
#delta-chart{flex:1.8;border-top:1px solid __C_BORDER__}
#cumdelta-chart{flex:1.8;border-top:1px solid __C_BORDER__}

/* -- sidebar --------------------- */
.sidebar{
  width:320px;min-width:320px;overflow-y:auto;
  border-left:1px solid __C_BORDER__;background:__C_BG__;
  display:flex;flex-direction:column;
}
.sidebar::-webkit-scrollbar{width:5px}
.sidebar::-webkit-scrollbar-track{background:__C_BG__}
.sidebar::-webkit-scrollbar-thumb{background:__C_BORDER__;border-radius:3px}

/* VP section */
.vp-section{padding:12px 14px;border-bottom:1px solid __C_BORDER__}
.vp-title{
  font-size:11px;font-weight:700;margin-bottom:8px;
  display:flex;align-items:center;gap:6px;
  text-transform:uppercase;letter-spacing:.5px;color:__C_TEXT_DIM__;
}
.vp-title::before{
  content:'';display:inline-block;width:3px;height:12px;
  background:__C_VPOC__;border-radius:1px;
}
.vp-row{display:flex;align-items:center;height:3px;margin:0;position:relative}
.vp-bar-bg{height:100%;border-radius:0 2px 2px 0;min-width:1px}
.vp-stats{
  display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:10px;font-size:11px;
}
.vp-stat{padding:5px 8px;background:rgba(42,46,57,.5);border-radius:4px}
.vp-stat-label{color:__C_TEXT_DIM__;font-size:10px;text-transform:uppercase;letter-spacing:.3px}
.vp-stat-value{font-weight:700;font-size:12px;margin-top:1px}

/* Explanation */
.explanation{padding:12px 14px;flex:1;font-size:11px;line-height:1.55}
.exp-section{margin-bottom:12px}
.exp-title{
  font-size:11px;font-weight:700;margin-bottom:5px;padding-bottom:3px;
  border-bottom:1px solid __C_BORDER__;text-transform:uppercase;
  letter-spacing:.4px;color:__C_TEXT_DIM__;
}
.exp-level{display:flex;align-items:center;gap:5px;padding:1px 0;font-size:11px}
.exp-swatch{display:inline-block;width:14px;height:2px;border-radius:1px;flex-shrink:0}
.exp-dim{color:__C_TEXT_DIM__;font-size:10px}
.exp-rule{padding-left:8px;color:__C_TEXT_DIM__;font-size:11px;margin:1px 0}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <span class="sym">__SYMBOL__</span>
  <span class="tf">M1</span>
  <span class="badge">Order Flow Scalper</span>
  <span style="flex:1"></span>
  <span class="tf" id="header-price"></span>
</div>

<!-- BODY -->
<div class="container">
  <div class="charts-col">
    <div id="main-chart" class="chart-pane">
      <div class="pane-label">Price + Volume + Key Levels</div>
    </div>
    <div id="delta-chart" class="chart-pane">
      <div class="pane-label">Bar Delta (Buy - Sell)</div>
    </div>
    <div id="cumdelta-chart" class="chart-pane">
      <div class="pane-label">Cumulative Delta</div>
    </div>
  </div>
  <div class="sidebar">
    <div class="vp-section">
      <div class="vp-title">Volume Profile</div>
      <div id="vp-bars"></div>
      <div class="vp-stats" id="vp-stats"></div>
    </div>
    <div class="explanation" id="explanation">__EXPLANATION__</div>
  </div>
</div>

<script>
// =============================================
//  DATA
// =============================================
var candleData   = __CANDLE_DATA__;
var volumeData   = __VOLUME_DATA__;
var deltaData    = __DELTA_DATA__;
var cumDeltaData = __CUMDELTA_DATA__;
var keyLevels    = __KEY_LEVELS__;
var markers      = __MARKERS__;
var vpData       = __VP_DATA__;

// =============================================
//  COMMON OPTIONS
// =============================================
var C_BG   = '__C_BG__';
var C_GRID = '__C_GRID__';
var C_BRDR = '__C_BORDER__';
var C_TXT  = '__C_TEXT__';

function chartOpts(el) {
  return {
    layout: {
      background: { type: 'solid', color: C_BG },
      textColor: C_TXT,
      fontSize: 11,
    },
    grid: {
      vertLines: { color: C_GRID },
      horzLines: { color: C_GRID },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' },
      horzLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' },
    },
    timeScale: {
      borderColor: C_BRDR,
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 5,
    },
    rightPriceScale: {
      borderColor: C_BRDR,
    },
    width:  el.clientWidth,
    height: el.clientHeight,
    handleScroll: { vertTouchDrag: false },
  };
}

// =============================================
//  MAIN CHART -- Candlestick + Volume
// =============================================
var mainEl = document.getElementById('main-chart');
var mainChart = LightweightCharts.createChart(mainEl, Object.assign({}, chartOpts(mainEl), {
  rightPriceScale: {
    borderColor: C_BRDR,
    scaleMargins: { top: 0.05, bottom: 0.18 },
  },
}));

var candleSeries = mainChart.addCandlestickSeries({
  upColor:         '__C_GREEN__',
  downColor:       '__C_RED__',
  borderUpColor:   '__C_GREEN__',
  borderDownColor: '__C_RED__',
  wickUpColor:     '__C_GREEN__',
  wickDownColor:   '__C_RED__',
});
candleSeries.setData(candleData);

// Volume overlay (bottom 18%)
var volSeries = mainChart.addHistogramSeries({
  priceFormat:  { type: 'volume' },
  priceScaleId: 'vol_overlay',
});
mainChart.priceScale('vol_overlay').applyOptions({
  scaleMargins: { top: 0.82, bottom: 0 },
});
volSeries.setData(volumeData);

// Key Levels as price lines
keyLevels.forEach(function(lv) {
  candleSeries.createPriceLine({
    price:            lv.price,
    color:            lv.color,
    lineWidth:        lv.lineWidth,
    lineStyle:        lv.lineStyle,
    axisLabelVisible: true,
    title:            lv.title,
  });
});

// Signal markers
if (markers.length > 0) {
  candleSeries.setMarkers(markers);
}

// Header: last price
if (candleData.length > 0) {
  var last = candleData[candleData.length - 1];
  var hdr = document.getElementById('header-price');
  var chg = last.close - last.open;
  hdr.style.color = chg >= 0 ? '__C_GREEN__' : '__C_RED__';
  hdr.textContent = last.close.toFixed(2) + '  (' + (chg >= 0 ? '+' : '') + chg.toFixed(2) + ')';
}

// =============================================
//  DELTA CHART
// =============================================
var deltaEl = document.getElementById('delta-chart');
var deltaChart = LightweightCharts.createChart(deltaEl, Object.assign({}, chartOpts(deltaEl), {
  rightPriceScale: {
    borderColor: C_BRDR,
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
}));
var deltaSeries = deltaChart.addHistogramSeries({
  priceFormat: { type: 'volume' },
});
if (deltaData.length > 0) deltaSeries.setData(deltaData);

// =============================================
//  CUMULATIVE DELTA CHART
// =============================================
var cumEl = document.getElementById('cumdelta-chart');
var cumChart = LightweightCharts.createChart(cumEl, Object.assign({}, chartOpts(cumEl), {
  rightPriceScale: {
    borderColor: C_BRDR,
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
}));
var cumSeries = cumChart.addAreaSeries({
  lineColor:   '__C_CUM_DELTA__',
  topColor:    'rgba(124,77,255,0.4)',
  bottomColor: 'rgba(124,77,255,0.04)',
  lineWidth:   2,
});
if (cumDeltaData.length > 0) cumSeries.setData(cumDeltaData);

// =============================================
//  SYNC: visible range across charts
// =============================================
var syncing = false;

function syncRange(src, t1, t2) {
  src.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
    if (syncing || !range) return;
    syncing = true;
    try { t1.timeScale().setVisibleLogicalRange(range); } catch(e){}
    try { t2.timeScale().setVisibleLogicalRange(range); } catch(e){}
    syncing = false;
  });
}
syncRange(mainChart,  deltaChart, cumChart);
syncRange(deltaChart, mainChart,  cumChart);
syncRange(cumChart,   mainChart,  deltaChart);

// =============================================
//  CROSSHAIR SYNC (best-effort)
// =============================================
function syncCH(src, srcS, pairs) {
  src.subscribeCrosshairMove(function(param) {
    if (syncing) return;
    syncing = true;
    pairs.forEach(function(p) {
      if (param.time) {
        try { p[0].setCrosshairPosition(NaN, param.time, p[1]); } catch(e){}
      } else {
        try { p[0].clearCrosshairPosition(); } catch(e){}
      }
    });
    syncing = false;
  });
}
syncCH(mainChart,  candleSeries, [[deltaChart, deltaSeries], [cumChart, cumSeries]]);
syncCH(deltaChart, deltaSeries,  [[mainChart, candleSeries], [cumChart, cumSeries]]);
syncCH(cumChart,   cumSeries,    [[mainChart, candleSeries], [deltaChart, deltaSeries]]);

// =============================================
//  VOLUME PROFILE SIDEBAR
// =============================================
(function() {
  var barsEl  = document.getElementById('vp-bars');
  var statsEl = document.getElementById('vp-stats');

  if (!vpData || vpData.length === 0) {
    barsEl.innerHTML = '<p style="color:__C_TEXT_DIM__;font-size:11px">No volume profile data</p>';
    return;
  }

  var sorted = vpData.slice().sort(function(a, b) { return b.price - a.price; });
  var maxVol = 0;
  sorted.forEach(function(d) { if (d.volume > maxVol) maxVol = d.volume; });

  sorted.forEach(function(d) {
    var row = document.createElement('div');
    row.className = 'vp-row';
    row.title = d.price.toFixed(2) + '  |  Vol: ' + d.volume.toFixed(0) + '  |  ' + d.pct.toFixed(1) + '%';

    var bar = document.createElement('div');
    bar.className = 'vp-bar-bg';
    bar.style.width = ((d.volume / maxVol) * 100).toFixed(1) + '%';

    if (d.isVpoc) {
      bar.style.background = '__C_VPOC__';
      bar.style.height = '5px';
    } else if (d.isVa) {
      bar.style.background = 'rgba(66,165,245,0.55)';
    } else {
      bar.style.background = 'rgba(120,120,255,0.2)';
    }
    row.appendChild(bar);
    barsEl.appendChild(row);
  });

  // Stats grid
  var vpoc = null, vah = 0, val = Infinity, totalVol = 0, totalBuy = 0;
  vpData.forEach(function(d) {
    totalVol += d.volume;
    totalBuy += d.buyVol;
    if (d.isVpoc) vpoc = d;
    if (d.isVa) {
      if (d.price > vah) vah = d.price;
      if (d.price < val) val = d.price;
    }
  });
  if (val === Infinity) val = 0;
  var buyPct = totalVol > 0 ? (totalBuy / totalVol * 100).toFixed(1) : '50.0';
  var volStr = totalVol > 1e6 ? (totalVol/1e6).toFixed(2)+'M' : (totalVol/1e3).toFixed(1)+'K';

  statsEl.innerHTML =
    '<div class="vp-stat"><div class="vp-stat-label">VPOC</div><div class="vp-stat-value" style="color:__C_VPOC__">' + (vpoc ? vpoc.price.toFixed(2) : '\u2014') + '</div></div>' +
    '<div class="vp-stat"><div class="vp-stat-label">Total Vol</div><div class="vp-stat-value">' + volStr + '</div></div>' +
    '<div class="vp-stat"><div class="vp-stat-label">VAH</div><div class="vp-stat-value" style="color:__C_VAH__">' + (vah > 0 ? vah.toFixed(2) : '\u2014') + '</div></div>' +
    '<div class="vp-stat"><div class="vp-stat-label">VAL</div><div class="vp-stat-value" style="color:__C_VAH__">' + (val > 0 ? val.toFixed(2) : '\u2014') + '</div></div>' +
    '<div class="vp-stat"><div class="vp-stat-label">Buy %</div><div class="vp-stat-value" style="color:__C_GREEN__">' + buyPct + '%</div></div>' +
    '<div class="vp-stat"><div class="vp-stat-label">Levels</div><div class="vp-stat-value">' + vpData.length + '</div></div>';
})();

// =============================================
//  RESIZE HANDLER
// =============================================
window.addEventListener('resize', function() {
  mainChart.applyOptions ({ width: mainEl.clientWidth,  height: mainEl.clientHeight  });
  deltaChart.applyOptions({ width: deltaEl.clientWidth, height: deltaEl.clientHeight });
  cumChart.applyOptions  ({ width: cumEl.clientWidth,   height: cumEl.clientHeight   });
});

// Fit content
mainChart.timeScale().fitContent();
deltaChart.timeScale().fitContent();
cumChart.timeScale().fitContent();
</script>
</body>
</html>
"""


# ==============================================================
#  Standalone Footprint Chart  (custom HTML grid)
# ==============================================================
def build_footprint_chart(
    fp_bars: List[FootprintBar] = None,
    bar_count: int = 20,
    output_html: str = "footprint_chart.html",
    auto_open: bool = True,
) -> Optional[str]:
    """Build a dedicated footprint (bid x ask) grid chart."""
    if fp_bars is None:
        conn = MT5Connector()
        conn.connect()
        try:
            puller = DataPuller(config.SYMBOL)
            tick_size = conn.spec.point if conn.spec else 0.01
            tick_data = puller.pull_ticks_session()
            bar_data = puller.pull_bars(config.TIMEFRAME_PRIMARY, count=bar_count)
            if tick_data is None or bar_data is None:
                log.error("No data for footprint chart")
                return None
            fp_builder = FootprintBuilder(tick_size)
            fp_bars = fp_builder.build_footprint(tick_data.df, bar_data.df)
        finally:
            conn.disconnect()

    if not fp_bars:
        log.error("No footprint bars to chart")
        return None

    fp_bars = fp_bars[-bar_count:]

    # Collect all price levels
    all_prices = set()
    for fp in fp_bars:
        all_prices.update(fp.levels.keys())
    if not all_prices:
        return None
    prices_sorted = sorted(all_prices, reverse=True)
    max_delta = max(
        (abs(lv.delta) for fp in fp_bars for lv in fp.levels.values()),
        default=1,
    )

    # Build HTML table rows
    rows_html = ""
    for price in prices_sorted:
        cells = f'<td class="fp-price">{price:.2f}</td>'
        for fp in fp_bars:
            lv = fp.levels.get(price)
            if lv is None:
                cells += '<td class="fp-cell fp-empty"></td>'
            else:
                delta = lv.delta
                intensity = min(abs(delta) / (max_delta + 1e-9), 1.0)
                if delta > 0:
                    bg = f"rgba(38,166,154,{0.15 + 0.55 * intensity:.2f})"
                else:
                    bg = f"rgba(239,83,80,{0.15 + 0.55 * intensity:.2f})"
                cells += (
                    f'<td class="fp-cell" style="background:{bg}" '
                    f'title="Bid:{lv.bid_vol:.0f} Ask:{lv.ask_vol:.0f} D:{delta:.0f}">'
                    f'<span class="fp-bid">{lv.bid_vol:.0f}</span>'
                    f'<span class="fp-x">x</span>'
                    f'<span class="fp-ask">{lv.ask_vol:.0f}</span>'
                    f'</td>'
                )
        rows_html += f"<tr>{cells}</tr>\n"

    # Header row
    header = "<th></th>"
    for fp in fp_bars:
        t = fp.bar_time
        label = t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)
        d = fp.bar_delta
        clr = C_GREEN if d >= 0 else C_RED
        header += (
            f'<th class="fp-time">{label}'
            f'<br><span style="color:{clr};font-size:9px">D{d:+.0f}</span></th>'
        )

    fp_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Footprint | {config.SYMBOL}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:{C_BG};color:{C_TEXT};font-family:'Consolas','Courier New',monospace;font-size:10px;overflow:auto}}
.fp-wrap{{padding:12px;overflow:auto}}
h2{{font-size:14px;margin-bottom:10px;font-family:-apple-system,'Segoe UI',sans-serif}}
table{{border-collapse:collapse}}
th,td{{border:1px solid {C_BORDER};padding:2px 4px;text-align:center;white-space:nowrap}}
th{{background:#1c2030;position:sticky;top:0;z-index:2;font-size:10px}}
.fp-price{{
  position:sticky;left:0;z-index:1;background:{C_BG};
  font-weight:700;text-align:right;padding-right:8px;min-width:80px;
}}
.fp-time{{min-width:65px}}
.fp-cell{{font-size:9px;min-width:70px}}
.fp-empty{{background:transparent}}
.fp-bid{{color:{C_RED}}}
.fp-ask{{color:{C_GREEN}}}
.fp-x{{color:{C_TEXT_DIM};margin:0 1px}}
</style></head><body>
<div class="fp-wrap">
<h2>Footprint Chart | {config.SYMBOL} M1 (Bid x Ask)</h2>
<table>
<thead><tr>{header}</tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div></body></html>"""

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(fp_html)

    if auto_open:
        import webbrowser
        webbrowser.open(f"file:///{os.path.abspath(out_path)}")

    log.info("Footprint chart saved -> %s", out_path)
    return out_path


# ==============================================================
#  CLI entry point
# ==============================================================
def main():
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Order Flow Scalper - TradingView Chart")
    parser.add_argument("--bars", type=int, default=100, help="Number of M1 bars (default: 100)")
    parser.add_argument("--footprint", action="store_true", help="Also generate footprint chart")
    parser.add_argument("--fp-bars", type=int, default=20, help="Footprint bar count (default: 20)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    parser.add_argument("-o", "--output", default="strategy_chart.html", help="Output HTML filename")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  ORDER FLOW SCALPER - TradingView Chart")
    print(f"  Symbol: {config.SYMBOL}  |  Bars: {args.bars}")
    print(f"{'='*60}\n")

    path = build_strategy_chart(
        bar_count=args.bars,
        output_html=args.output,
        auto_open=not args.no_open,
    )

    if path:
        print(f"\n  Chart saved -> {path}")
    else:
        print("\n  Failed to build chart -- check logs")
        sys.exit(1)

    if args.footprint:
        fp_path = build_footprint_chart(
            bar_count=args.fp_bars,
            output_html="footprint_chart.html",
            auto_open=not args.no_open,
        )
        if fp_path:
            print(f"  Footprint chart saved -> {fp_path}")


if __name__ == "__main__":
    main()
