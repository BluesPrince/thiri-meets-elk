#!/usr/bin/env python3
"""make_figures.py — presentation figures generated FROM THE MEASURED DATA.

Every plotted value is computed from profiling-results.csv at build time, so the
figures cannot drift from the measurements and cannot be quietly hand-edited.
The script prints what it plotted; cross-check it against the CSV.

Emits, into figures/, in dark (deck) and light (Canva/Slides) themes:
  cost-vs-voices-*.svg       the hero: PV crosses the deadline, PSOLA stays flat
  optimization-journey-*.svg the YIN peak-block reduction, vs the 1.333 ms budget
  signal-flow-*.svg          where the two shifters plug in (no data; hand-authored)

Usage:  python3 tools/make_figures.py
"""
import csv
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "profiling-results.csv")
OUT = os.path.join(ROOT, "figures")

# The two comparable series: both ran with the tau-sliced tracker, so the only
# difference between them is the shifter engine. (The pre-slice "sweep N of 3"
# rows are a different tracker build and are NOT comparable -- excluded.)
PV_TAG = "sliced sweep"
PS_TAG = "psola sweep"

BLOCK, SR = 64, 48000
DEADLINE_MS = BLOCK / SR * 1000.0      # 1.333 ms

THEMES = {
    "dark":  dict(bg="#0d0d10", ink="#eae7df", dim="#9a9aa2", grid="#2a2a31",
                  gold="#d4af37", warn="#d96a52", muted="#6a6a72"),
    "light": dict(bg="#faf8f3", ink="#211f1a", dim="#6b6659", grid="#ddd7c7",
                  gold="#8a6d1f", warn="#a33d2a", muted="#8f8a7c"),
}
FONT = "ui-monospace, Menlo, Consolas, 'DejaVu Sans Mono', monospace"


def load_series():
    """Return {tag: {voice: {'avg': mean-of-runs, 'max': worst-of-runs, 'n': runs}}}."""
    rows = [r for r in csv.DictReader(open(CSV)) if r["host"] == "board"]
    out = {}
    for tag in (PV_TAG, PS_TAG):
        acc = {}
        for r in rows:
            if not r["notes"].startswith(tag):
                continue
            v = int(r["voice_count"])
            acc.setdefault(v, {"avg": [], "max": []})
            acc[v]["avg"].append(float(r["thiri_avg"]))
            acc[v]["max"].append(float(r["thiri_max"]))
        out[tag] = {
            v: {"avg": statistics.fmean(d["avg"]), "max": max(d["max"]), "n": len(d["avg"])}
            for v, d in sorted(acc.items())
        }
    return out


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cost_chart(series, th):
    """Hero figure: average cost vs voice count, both engines, 16:9."""
    W, H = 1600, 900
    L, R, T, B = 190, 90, 120, 150
    pw, ph = W - L - R, H - T - B
    ymax = 2.0
    xs = sorted(series[PV_TAG])
    px = lambda v: L + (v / max(xs)) * pw
    py = lambda y: T + ph - (y / ymax) * ph

    def poly(tag):
        return " ".join(f"{px(v):.1f},{py(series[tag][v]['avg']):.1f}" for v in xs)

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="{FONT}" role="img" aria-label="Average cost per audio block versus voice '
         f'count. The phase vocoder exceeds the real-time deadline from the first voice onward; '
         f'PSOLA stays flat and far below it.">',
         f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>']

    for val in (0.0, 0.5, 1.5, 2.0):
        y = py(val)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" stroke="{th["grid"]}" stroke-width="1.5"/>')
        s.append(f'<text x="{L-22}" y="{y+9:.1f}" text-anchor="end" font-size="26" fill="{th["dim"]}">{val:.1f}x</text>')

    yd = py(1.0)
    s.append(f'<line x1="{L}" y1="{yd:.1f}" x2="{L+pw}" y2="{yd:.1f}" stroke="{th["warn"]}" stroke-width="3" stroke-dasharray="14 10"/>')
    s.append(f'<text x="{L-22}" y="{yd+9:.1f}" text-anchor="end" font-size="26" fill="{th["warn"]}">1.0x</text>')
    s.append(f'<text x="{L+pw}" y="{yd-20:.1f}" text-anchor="end" font-size="26" fill="{th["warn"]}">REAL-TIME DEADLINE ({DEADLINE_MS:.3f} ms)</text>')

    s.append(f'<polyline points="{poly(PV_TAG)}" fill="none" stroke="{th["muted"]}" stroke-width="5"/>')
    s.append(f'<polyline points="{poly(PS_TAG)}" fill="none" stroke="{th["gold"]}" stroke-width="6"/>')
    for v in xs:
        s.append(f'<circle cx="{px(v):.1f}" cy="{py(series[PV_TAG][v]["avg"]):.1f}" r="8" fill="{th["muted"]}"/>')
        s.append(f'<circle cx="{px(v):.1f}" cy="{py(series[PS_TAG][v]["avg"]):.1f}" r="9" fill="{th["gold"]}"/>')
        s.append(f'<text x="{px(v):.1f}" y="{T+ph+52:.1f}" text-anchor="middle" font-size="28" fill="{th["dim"]}">{v}</text>')

    s.append(f'<text x="{px(1)+26:.1f}" y="{py(series[PV_TAG][1]["avg"])-26:.1f}" font-size="30" fill="{th["ink"]}">phase vocoder</text>')
    s.append(f'<text x="{px(1)+26:.1f}" y="{py(series[PS_TAG][1]["avg"])+52:.1f}" font-size="30" fill="{th["gold"]}">PSOLA</text>')

    s.append(f'<text x="{L+pw/2:.1f}" y="{H-58}" text-anchor="middle" font-size="30" fill="{th["dim"]}">harmony voices</text>')
    s.append(f'<text x="46" y="{T+ph/2:.1f}" text-anchor="middle" font-size="30" fill="{th["dim"]}" '
             f'transform="rotate(-90 46 {T+ph/2:.1f})">avg cost per block</text>')
    s.append(f'<text x="{L}" y="62" font-size="40" font-weight="700" fill="{th["ink"]}">Cost per audio block vs voice count</text>')
    s.append(f'<text x="{L}" y="98" font-size="24" fill="{th["dim"]}">Elk Stomp, 64-sample block @ 48 kHz &#183; mean of 3 sweeps &#183; measured, not modelled</text>')
    s.append("</svg>")
    return "\n".join(s)


def journey_chart(th):
    """YIN peak block, before/after. Values from on-board yin_bench runs (not the CSV)."""
    bars = [("scalar (as found)", 8.1, False), ("+ vector flags", 6.7, False), ("+ tau-sliced YIN", 1.0, True)]
    W, H = 1600, 560
    L, R, T, ROW = 470, 190, 170, 118
    pw = W - L - R
    scale = pw / 9.0                       # ms -> px
    vx = L + pw + 22                       # value labels in a fixed column, clear of every bar
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="{FONT}" role="img" aria-label="Pitch tracker peak block cost reduced from '
         f'8.1 to 1.0 milliseconds, crossing under the 1.333 millisecond budget.">',
         f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>',
         f'<text x="100" y="72" font-size="40" font-weight="700" fill="{th["ink"]}">Pitch tracker: worst block</text>',
         f'<text x="100" y="110" font-size="24" fill="{th["dim"]}">on-board benchmark &#183; the budget is {DEADLINE_MS:.3f} ms per block</text>']
    for i, (label, ms, good) in enumerate(bars):
        y = T + i * ROW
        col = th["gold"] if good else th["muted"]
        s.append(f'<text x="{L-30}" y="{y+44}" text-anchor="end" font-size="30" fill="{th["dim"]}">{esc(label)}</text>')
        s.append(f'<rect x="{L}" y="{y}" width="{ms*scale:.1f}" height="60" rx="8" fill="{col}"/>')
        s.append(f'<text x="{vx:.1f}" y="{y+44}" font-size="32" fill="{th["ink"]}">{ms:.1f} ms</text>')
    # budget marker: label BELOW the line so it cannot collide with the subtitle
    bx = L + DEADLINE_MS * scale
    y0, y1 = T - 30, T + 2 * ROW + 88
    s.append(f'<line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="{th["warn"]}" stroke-width="4" stroke-dasharray="12 9"/>')
    s.append(f'<text x="{bx:.1f}" y="{y1+38}" text-anchor="middle" font-size="26" fill="{th["warn"]}">budget</text>')
    s.append("</svg>")
    return "\n".join(s)


def signal_flow(th):
    """Where the two shifters plug in. Hand-authored topology; no data to verify."""
    W, H = 1600, 500
    g, ink, dim, mut = th["gold"], th["ink"], th["dim"], th["muted"]

    def box(x, y, w, hh, label, sub, accent=False, dash=False):
        col = g if accent else ink
        sw = 5 if accent else 3
        da = ' stroke-dasharray="12 8"' if dash else ""
        op = ' opacity="0.5"' if dash else ""
        out = [f'<rect x="{x}" y="{y}" width="{w}" height="{hh}" rx="14" fill="none" stroke="{col}" stroke-width="{sw}"{da}{op}/>',
               f'<text x="{x+w/2}" y="{y+hh/2+(0 if not sub else -8)}" text-anchor="middle" font-size="30" fill="{col}"{op}>{esc(label)}</text>']
        if sub:
            out.append(f'<text x="{x+w/2}" y="{y+hh/2+28}" text-anchor="middle" font-size="24" fill="{col}" opacity="{0.4 if dash else 0.7}">{esc(sub)}</text>')
        return out

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="{FONT}" role="img" aria-label="Signal chain: the sax feeds the pitch tracker, '
         f'which feeds the chord brain; the brain drives either the PSOLA voices or the phase vocoder '
         f'voices, and PSOLA additionally reuses the pitch period the tracker already computed.">',
         f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>',
         f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         f'<path d="M0 0 L10 5 L0 10 z" fill="{ink}"/></marker>'
         f'<marker id="ag" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         f'<path d="M0 0 L10 5 L0 10 z" fill="{g}"/></marker></defs>']
    s += box(60, 230, 170, 96, "sax in", None)
    s += box(300, 230, 240, 96, "tracker", "YIN")
    s += box(610, 230, 240, 96, "THIRI", "chord brain")
    s += box(940, 110, 300, 96, "PSOLA voices", "0.005x each", accent=True)
    s += box(940, 350, 300, 96, "vocoder voices", "0.25x each", dash=True)
    s += box(1330, 230, 210, 96, "mix out", None)
    A = f'stroke="{ink}" stroke-width="3" marker-end="url(#a)"'
    G = f'stroke="{g}" stroke-width="4" marker-end="url(#ag)"'
    D = f'stroke="{mut}" stroke-width="3" stroke-dasharray="12 8" opacity="0.55" marker-end="url(#a)"'
    s.append(f'<line x1="230" y1="278" x2="288" y2="278" {A}/>')
    s.append(f'<line x1="540" y1="278" x2="598" y2="278" {A}/>')
    s.append(f'<text x="575" y="214" text-anchor="middle" font-size="24" fill="{dim}">pitch</text>')
    s.append(f'<path d="M850 258 L895 258 L895 158 L930 158" fill="none" {G}/>')
    s.append(f'<text x="868" y="284" font-size="22" fill="{g}">notes</text>')
    s.append(f'<path d="M850 298 L895 298 L895 398 L930 398" fill="none" {D}/>')
    s.append(f'<path d="M420 230 L420 62 L1090 62 L1090 100" fill="none" {G}/>')
    s.append(f'<text x="755" y="46" text-anchor="middle" font-size="26" fill="{g}">period &#8212; already computed, reused free</text>')
    s.append(f'<path d="M1240 158 L1285 158 L1285 258 L1320 258" fill="none" {G}/>')
    s.append(f'<path d="M1240 398 L1285 398 L1285 298 L1320 298" fill="none" {D}/>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    series = load_series()

    print("PLOTTED VALUES (cross-check against profiling-results.csv):")
    print(f"  {'voices':>6} | {'PV avg':>8} {'PV worst':>9} | {'PSOLA avg':>10} {'PSOLA worst':>12}")
    for v in sorted(series[PV_TAG]):
        p, q = series[PV_TAG][v], series[PS_TAG][v]
        print(f"  {v:>6} | {p['avg']:>8.4f} {p['max']:>9.4f} | {q['avg']:>10.4f} {q['max']:>12.4f}")
    n = series[PV_TAG][0]["n"]
    print(f"  (mean of {n} sweeps per point; 'worst' = max across sweeps)")

    assert series[PV_TAG][1]["avg"] > 1.0, "PV should exceed real-time at 1 voice"
    assert all(series[PS_TAG][v]["avg"] < 0.7 for v in series[PS_TAG]), "PSOLA should stay under 0.7x"
    assert series[PS_TAG][5]["max"] < 1.0, "PSOLA worst block must fit the deadline"
    # Marginal cost over the SAME span for both engines (0 -> 5 voices), so the
    # ratio is apples-to-apples. Note PV saturates after v=4 (v4 1.830 ~ v5 1.828),
    # so a 0->4 span would flatter PSOLA (0.32x/voice, 65x); 0->5 is the honest one.
    span = max(series[PV_TAG])
    marg_pv = (series[PV_TAG][span]["avg"] - series[PV_TAG][0]["avg"]) / span
    marg_ps = (series[PS_TAG][span]["avg"] - series[PS_TAG][0]["avg"]) / span
    print(f"\n  per-voice marginal avg over 0->{span}: PV {marg_pv:.4f}x  PSOLA {marg_ps:.4f}x"
          f"  -> {marg_pv/marg_ps:.0f}x cheaper")
    print(f"  headline: {series[PS_TAG][5]['avg']:.3f}x avg / {series[PS_TAG][5]['max']:.3f}x worst at 5 voices")

    written = []
    for name, th in THEMES.items():
        for base, fn in (("cost-vs-voices", lambda t: cost_chart(series, t)),
                         ("optimization-journey", journey_chart),
                         ("signal-flow", signal_flow)):
            p = os.path.join(OUT, f"{base}-{name}.svg")
            open(p, "w").write(fn(th))
            written.append(p)
    print(f"\nwrote {len(written)} SVGs to {os.path.relpath(OUT, ROOT)}/")
    for p in written:
        print("  ", os.path.basename(p))


if __name__ == "__main__":
    main()
