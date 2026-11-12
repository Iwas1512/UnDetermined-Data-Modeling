"""Step 4: build app/surface_viewer.html, a self-contained interactive page (first version).

Pick an index and a date: 3D implied-vol surface, smiles at 1/7/30/90 days, ATM term structure, and the
30-day implied vs realized history.  Only fitted SVI parameters and daily summary numbers are embedded
(no raw quotes).  Open the file in a browser; Plotly loads from a CDN.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "app" / "surface_viewer.html"
NAME = {"SPXW": "SPX", "NDXP": "NDX"}


def r6(x):
    return None if not np.isfinite(x) else float(f"{x:.6g}")


def payload() -> dict:
    daily = pd.read_parquet(DATA / "daily.parquet")
    out = {}
    for root, name in NAME.items():
        f = pd.read_parquet(DATA / f"svi_{root}.parquet").sort_values(["date", "T"])
        d = daily[daily.root == root].set_index("date")
        days = {}
        for date, g in f.groupby("date", sort=True):
            days[str(date)] = [[r6(v) for v in row] for row in
                               g[["T", "a", "b", "rho", "m", "s", "k_min", "k_max", "atm_iv"]].to_numpy(float)]
        out[name] = {
            "dates": list(days),
            "fits": days,
            "iv30": [r6(v) for v in d["iv30"].reindex(pd.Index(f["date"].unique())).to_numpy(float)],
            "rv30": [r6(v) for v in d["rv30_fwd"].reindex(pd.Index(f["date"].unique())).to_numpy(float)],
            "skew30": [r6(v) for v in d["skew30"].reindex(pd.Index(f["date"].unique())).to_numpy(float)],
        }
    return out


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Volatility Surface Viewer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"></script>
<style>
:root{--bg:#fcfcfb;--panel:#ffffff;--ink:#0b0b0b;--muted:#52514e;--line:#e6e5e1;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--grey:#9a9994}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--panel:#222220;--ink:#f0efec;--muted:#c3c2b7;--line:#3a3936;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--grey:#8a8984}}
:root[data-theme="dark"]{--bg:#1a1a19;--panel:#222220;--ink:#f0efec;--muted:#c3c2b7;--line:#3a3936;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--grey:#8a8984}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:18px 16px 6px;max-width:1280px;margin:auto}h1{font-size:20px;margin:0 0 4px}header p{margin:0;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:10px 16px;max-width:1280px;margin:auto}
select,button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer}
input[type=range]{flex:1;min-width:200px;accent-color:var(--s1)}#dlabel{font-variant-numeric:tabular-nums;min-width:96px;font-weight:600}
.stats{display:flex;gap:18px;flex-wrap:wrap;padding:0 16px;max-width:1280px;margin:auto;color:var(--muted)}.stats b{color:var(--ink)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px 16px 24px;max-width:1280px;margin:auto}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px;min-height:360px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
footer{max-width:1280px;margin:auto;padding:0 16px 24px;color:var(--muted);font-size:12px}
</style></head><body>
<header><h1>Implied volatility surfaces: SPX &amp; NDX index options</h1>
<p>CS 418, Team UIC Traders. SVI fits to end-of-day OPRA closing quotes, Oct 2025 to Jun 2026.</p></header>
<div class="controls">
<label>Index <select id="root"><option>SPX</option><option>NDX</option></select></label>
<button id="prev" aria-label="previous day">&#8592;</button><input id="slider" type="range" min="0" value="0" aria-label="date"><button id="next" aria-label="next day">&#8594;</button>
<span id="dlabel"></span></div>
<div class="stats" id="stats"></div>
<div class="grid"><div class="card" id="surf"></div><div class="card" id="smiles"></div><div class="card" id="term"></div><div class="card" id="hist"></div></div>
<footer>Surface: total variance interpolated linearly in maturity between fitted expiries (7 to 180 days). Smiles drawn only over each expiry's quoted strike range.
Realized vol = volatility of the index over the following 30 calendar days (blank for the last month).</footer>
<script>
const DATA = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const w = (p,k) => p[1] + p[2]*(p[3]*(k-p[4]) + Math.sqrt((k-p[4])**2 + p[5]**2));
const ivAt = (p,k) => Math.sqrt(Math.max(w(p,k),1e-12)/p[0]);
const $ = id => document.getElementById(id);
let root = "SPX", idx = 0;
function layout(title, x, y, extra={}) {
  return Object.assign({title:{text:title,font:{size:14,color:css('--ink')}}, paper_bgcolor:css('--panel'), plot_bgcolor:css('--panel'),
    font:{color:css('--muted'),size:11}, margin:{l:52,r:14,t:40,b:44}, xaxis:{title:x,gridcolor:css('--line'),zeroline:false},
    yaxis:{title:y,gridcolor:css('--line'),zeroline:false}, legend:{orientation:'h',y:-0.22}, hovermode:'closest'}, extra);
}
const cfg = {displaylogo:false,responsive:true};
function draw() {
  const R = DATA[root], date = R.dates[idx], F = R.fits[date];
  $('dlabel').textContent = date;
  const iv30 = R.iv30[idx], rv30 = R.rv30[idx], sk = R.skew30[idx];
  $('stats').innerHTML = `<span>30-day ATM IV <b>${iv30!=null?(iv30*100).toFixed(1)+'%':'n/a'}</b></span>`+
    `<span>realized next 30d <b>${rv30!=null?(rv30*100).toFixed(1)+'%':'n/a'}</b></span>`+
    `<span>30-day skew (95%&minus;105%) <b>${sk!=null?(sk*100).toFixed(1)+' pts':'n/a'}</b></span><span>expiries fitted <b>${F.length}</b></span>`;
  // surface
  const ks = Array.from({length:50},(_,i)=>-0.15+0.2*i/49), Tmin = 7/365, Tmax = Math.min(180/365, F[F.length-1][0]);
  const Ts = Array.from({length:40},(_,i)=>Tmin+(Tmax-Tmin)*i/39);
  const Z = Ts.map(T => ks.map(k => {
    let j = F.findIndex(p => p[0] >= T); if (j <= 0) j = 1;
    const p0 = F[j-1], p1 = F[j], t = (T-p0[0])/(p1[0]-p0[0]);
    const wv = w(p0,k)*(1-t) + w(p1,k)*t; return Math.sqrt(Math.max(wv,1e-12)/T)*100; }));
  Plotly.react('surf', [{type:'surface', x:ks.map(k=>Math.exp(k)*100), y:Ts.map(T=>T*365), z:Z, colorscale:'Blues', reversescale:true,
    showscale:false, hovertemplate:'strike %{x:.1f}% of fwd<br>%{y:.0f} days<br>IV %{z:.1f}%<extra></extra>'}],
    layout('Surface', '', '', {scene:{xaxis:{title:'strike, % of forward'}, yaxis:{title:'days'}, zaxis:{title:'IV %'},
    camera:{eye:{x:-1.5,y:-1.5,z:0.8}}}, margin:{l:0,r:0,t:40,b:0}}), cfg);
  // smiles
  const cols = [css('--s1'),css('--s2'),css('--s3'),css('--s4')], tr = [];
  [1,7,30,90].forEach((d,i) => {
    const p = F.reduce((b,q)=>Math.abs(q[0]*365-d)<Math.abs(b[0]*365-d)?q:b);
    const sd = p[8]*Math.sqrt(p[0]), lo = Math.max(p[6], -4.5*sd), hi = Math.min(p[7], 2.5*sd);
    const kk = Array.from({length:120},(_,j)=>lo+(hi-lo)*j/119);
    tr.push({x:kk.map(k=>Math.exp(k)*100), y:kk.map(k=>ivAt(p,k)*100), mode:'lines', line:{color:cols[i],width:2},
      name:`${Math.round(p[0]*365)}-day`, hovertemplate:'strike %{x:.1f}%<br>IV %{y:.1f}%<extra>%{fullData.name}</extra>'});
  });
  Plotly.react('smiles', tr, layout('Smiles by expiry', 'strike, % of forward', 'implied vol %'), cfg);
  // term structure
  Plotly.react('term', [{x:F.map(p=>p[0]*365), y:F.map(p=>p[8]*100), mode:'lines+markers', line:{color:css('--s1'),width:2},
    marker:{size:6}, hovertemplate:'%{x:.0f} days: %{y:.1f}%<extra></extra>', name:'ATM IV'}],
    layout('ATM implied vol by expiry', 'days to expiry', 'ATM IV %', {xaxis:{title:'days to expiry', type:'log', gridcolor:css('--line')}}), cfg);
  // history
  Plotly.react('hist', [
    {x:R.dates, y:R.iv30.map(v=>v==null?null:v*100), mode:'lines', name:'30-day implied', line:{color:css('--s1'),width:2}},
    {x:R.dates, y:R.rv30.map(v=>v==null?null:v*100), mode:'lines', name:'realized, next 30 days', line:{color:css('--ink'),width:1.5}}],
    layout('Implied vs realized (30 days)', '', 'vol %', {hovermode:'x unified', shapes:[{type:'line', x0:date, x1:date, yref:'paper', y0:0, y1:1,
      line:{color:css('--grey'),width:1,dash:'dot'}}]}), cfg);
}
function setRoot(r){ const d = DATA[root].dates[idx]; root = r; const ds = DATA[root].dates;
  $('slider').max = ds.length-1; idx = Math.max(0, ds.indexOf(d)); if (idx<0) idx = ds.length-1; $('slider').value = idx; draw(); }
$('root').onchange = e => setRoot(e.target.value);
$('slider').oninput = e => { idx = +e.target.value; draw(); };
$('prev').onclick = () => { idx = Math.max(0, idx-1); $('slider').value = idx; draw(); };
$('next').onclick = () => { idx = Math.min(DATA[root].dates.length-1, idx+1); $('slider').value = idx; draw(); };
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
$('slider').max = DATA[root].dates.length-1; idx = DATA[root].dates.indexOf('2026-03-27'); if (idx<0) idx=0; $('slider').value = idx; draw();
</script></body></html>
"""


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(HTML.replace("__DATA__", json.dumps(payload(), separators=(",", ":"))), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
