"""Plausibilitätscheck der erzeugten Daten in docs/data.

  python scanner/check_data.py docs

Bricht mit Fehlercode 1 ab, wenn Daten kaputt sind (NaN, fehlende Dateien, unlogische Spannen),
damit der tägliche Workflow nichts Fehlerhaftes veröffentlicht. Extreme Potenziale sind nur Hinweise.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

D = Path(sys.argv[1]) / "data"
problems = []


def walk(o, path):
    if isinstance(o, float) and not math.isfinite(o):
        problems.append(f"NaN/Inf in {path}")
    elif isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]")


latest = json.loads((D / "latest.json").read_text())
walk(latest, "latest")
print("Stand:", latest["date"], latest["generated_at"])
for k in ("innovation", "buffett"):
    sec = latest[k]
    print(f"{k}: {len(sec['picks'])} Vorschläge, {len(sec['ranking'])} im Ranking")
    if len(sec["picks"]) != 6:
        problems.append(f"{k}: nicht 6 Vorschläge")

idx = json.loads((D / "lookup" / "index.json").read_text())["stocks"]
print("Such-Index:", len(idx), "Aktien")
styles, outl, nofair, divs = Counter(), [], [], []
for e in idx:
    f = D / "lookup" / f"{e['file']}.json"
    if not f.exists():
        problems.append(f"Datei fehlt: {f.name}")
        continue
    a = json.loads(f.read_text())
    walk(a, a["symbol"])
    styles[a["style"]] += 1
    for k in ("buffett", "innovation"):
        b = a[k]
        if not 0 <= b["score"] <= 100:
            problems.append(f"{a['symbol']} {k} Score {b['score']}")
        fv, lo, hi = b.get("fair_value"), b.get("fair_low"), b.get("fair_high")
        if fv is None:
            nofair.append(f"{a['symbol']}/{k}")
            continue
        if fv < 0 or (lo is not None and hi is not None and not (lo <= fv <= hi)):
            problems.append(f"{a['symbol']} {k}: Spanne unlogisch {lo} / {fv} / {hi}")
        prim = (k == "buffett") == (a["primary"] == "buffett")
        if prim and (b["potential"] > 2.0 or b["potential"] < -0.85):
            outl.append(f"{a['symbol']} ({k}) {b['potential']:+.0%}")
    for r in a["buffett"]["reasons"]:
        if "Dividende" in r:
            divs.append(r)
    if not a.get("verdict") or not a.get("style"):
        problems.append(f"{a['symbol']}: Einstufung fehlt")

print("Einstufungen:", dict(styles))
print("Ohne fairen Wert:", len(nofair), nofair[:10])
print("Extreme Potenziale (Haupt-Bewertung > +200 % oder < -85 %):", outl)
print("Dividenden-Texte:", sorted(set(divs)))
bp = [x["potential"] for x in latest["buffett"]["ranking"] if x["potential"] is not None]
print(f"Buffett: {sum(p > 0 for p in bp)}/{len(bp)} unterbewertet, Median {sorted(bp)[len(bp) // 2]:+.0%}")
print("Labels:", dict(Counter(x["label"] for x in latest["buffett"]["ranking"])))
for s in ("GOOGL", "TSM", "MSFT", "META", "V", "KO", "AAPL", "NVO", "PLTR", "RKLB", "CVX", "CRWV", "NBIS"):
    f = D / "lookup" / f"{s}.json"
    if not f.exists():
        continue
    a = json.loads(f.read_text())
    b = a[a["primary"]]
    print(f"  {s:5} {a['price']:8.2f} fair {b['fair_value'] or 0:8.0f} {b['potential'] or 0:+5.0%} | {a['style']} | "
          f"B {a['buffett']['score']} {a['buffett']['label']} {a['buffett']['rules_met']} | I {a['innovation']['score']} | Risiko {b['risk']['name']}")
if len(idx) < 50:
    problems.append(f"nur {len(idx)} Aktien im Such-Index")
print("\nPROBLEME:", problems if problems else "keine")
sys.exit(1 if problems else 0)
