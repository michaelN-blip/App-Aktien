"""Täglicher Aktien-Scanner.

Holt Kennzahlen über yfinance, bewertet jede Aktie nach zwei Strategien
und schreibt das Ergebnis nach docs/data/ (für die Web-App).

  python scanner/scan.py            # echter Scan
  python scanner/scan.py --limit 10 # schneller Test mit wenigen Tickern
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scoring import score_buffett, score_innovation  # noqa: E402
from universe import INNOVATION, VALUE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
PICKS_PER_DAY = 6
POOL_SIZE = 15  # aus den besten 15 werden täglich 6 gezogen (gewichtet nach Score)

_fx_cache: dict[str, float] = {}


def fx_rate(src: str | None, dst: str | None) -> float:
    """Wechselkurs src -> dst (z. B. EUR -> USD)."""
    if not src or not dst or src == dst:
        return 1.0
    key = f"{src}{dst}"
    if key not in _fx_cache:
        import yfinance as yf
        try:
            _fx_cache[key] = float(yf.Ticker(f"{key}=X").fast_info["lastPrice"])
        except Exception:
            _fx_cache[key] = float("nan")
    return _fx_cache[key]


def _row(df, *names):
    """Zeile aus einem yfinance-Finanz-DataFrame (neueste zuerst) als Liste."""
    if df is None or getattr(df, "empty", True):
        return []
    for n in names:
        if n in df.index:
            vals = [v for v in df.loc[n].tolist() if v is not None and not (isinstance(v, float) and math.isnan(v))]
            return [float(v) for v in vals]
    return []


def _byyear(df, *names) -> dict:
    """Zeile eines Jahres-Finanzberichts als {Jahr: Wert} (fehlende Werte weggelassen)."""
    if df is None or getattr(df, "empty", True):
        return {}
    for n in names:
        if n in df.index:
            out = {}
            for col, v in df.loc[n].items():
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    out[int(getattr(col, "year", 0) or 0)] = float(v)
            if out:
                return out
    return {}


def fetch(symbol: str) -> dict | None:
    import yfinance as yf

    t = yf.Ticker(symbol)
    info = t.info or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not price or not info.get("marketCap"):
        return None

    try:
        inc = t.income_stmt
    except Exception:
        inc = None
    net_income = _row(inc, "Net Income", "Net Income Common Stockholders")
    revenue = _row(inc, "Total Revenue", "Operating Revenue")
    rnd = _row(inc, "Research And Development")
    try:
        cf = t.cashflow
    except Exception:
        cf = None
    try:
        bs = t.balance_sheet
    except Exception:
        bs = None
    history = {
        "revenue": _byyear(inc, "Total Revenue", "Operating Revenue"),
        "gross_profit": _byyear(inc, "Gross Profit"),
        "net_income": _byyear(inc, "Net Income", "Net Income Common Stockholders"),
        "operating_cf": _byyear(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
        "capex": _byyear(cf, "Capital Expenditure"),
        "depreciation": _byyear(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion"),
        "free_cf": _byyear(cf, "Free Cash Flow"),
        "total_assets": _byyear(bs, "Total Assets"),
        "equity": _byyear(bs, "Stockholders Equity", "Common Stock Equity"),
    }

    rate = fx_rate(info.get("financialCurrency"), info.get("currency"))
    fx = rate if math.isfinite(rate) else None

    return {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "currency": info.get("currency", "USD"),
        "price": float(price),
        "market_cap": info.get("marketCap"),
        "shares": info.get("sharesOutstanding"),
        "summary": (info.get("longBusinessSummary") or "")[:400],
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": (info["debtToEquity"] / 100) if info.get("debtToEquity") is not None else None,
        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "insider_pct": info.get("heldPercentInsiders"),
        "target_price": info.get("targetMeanPrice"),
        "fifty_two_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_low": info.get("fiftyTwoWeekLow"),
        "ma200": info.get("twoHundredDayAverage"),
        # Finanzzahlen in Handelswährung umgerechnet
        "free_cashflow": info["freeCashflow"] * fx if info.get("freeCashflow") and fx else None,
        "total_cash": info["totalCash"] * fx if info.get("totalCash") and fx else None,
        "total_debt": info["totalDebt"] * fx if info.get("totalDebt") is not None and fx else None,
        "revenue_ttm": info["totalRevenue"] * fx if info.get("totalRevenue") and fx else None,
        "history": history,
        "fx": fx,
        "net_income_hist": net_income[:5],
        "revenue_hist": revenue[:5],
        "rnd_latest": rnd[0] if rnd else None,
        "revenue_latest": revenue[0] if revenue else None,
    }


def daily_pick(ranked: list[dict], day: str, salt: str) -> list[dict]:
    """Gewichtete Zufallsauswahl aus den Top-Kandidaten – täglich anders, aber reproduzierbar."""
    pool = ranked[:POOL_SIZE]
    rng = random.Random(f"{day}-{salt}")
    picks = []
    while pool and len(picks) < PICKS_PER_DAY:
        weights = [max(p["score"], 1) ** 2 for p in pool]
        choice = rng.choices(pool, weights=weights, k=1)[0]
        picks.append(choice)
        pool.remove(choice)
    return sorted(picks, key=lambda p: -p["score"])


def clean(obj):
    """NaN/Inf -> None, damit gültiges JSON entsteht."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else round(obj, 4)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


MORNINGSTAR_CSV = Path(__file__).parent / "morningstar.csv"
MOAT_DE = {"wide": "Breit", "narrow": "Schmal", "none": "Kein"}
UNC_DE = {"low": "Niedrig", "medium": "Mittel", "high": "Hoch", "very high": "Sehr hoch", "extreme": "Extrem"}


def load_morningstar() -> dict:
    """Eigene Morningstar-Notizen: symbol,fair_value,stars,moat,uncertainty,date."""
    import csv
    if not MORNINGSTAR_CSV.exists():
        return {}
    out = {}
    with MORNINGSTAR_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            try:
                fv = float((row.get("fair_value") or "").replace(",", "."))
            except ValueError:
                fv = None
            stars = (row.get("stars") or "").strip()
            moat = (row.get("moat") or "").strip().lower()
            unc = (row.get("uncertainty") or "").strip().lower()
            out[sym] = {"fair_value": fv, "stars": int(stars) if stars.isdigit() else None,
                        "moat": MOAT_DE.get(moat, moat or None), "uncertainty": UNC_DE.get(unc, unc or None),
                        "date": (row.get("date") or "").strip() or None}
    return out


def attach_morningstar(results: list[dict], ms: dict) -> None:
    for r in results:
        m = ms.get(r["symbol"])
        if not m:
            continue
        m = dict(m)
        if m["fair_value"]:
            m["potential"] = m["fair_value"] / r["price"] - 1
            if r.get("fair_value"):
                m["vs_model"] = r["fair_value"] / m["fair_value"] - 1
        r["morningstar"] = m


def build(stocks_innov: list[dict], stocks_value: list[dict], day: str, previous: dict | None) -> dict:
    innov = [score_innovation(s, INNOVATION.get(s["symbol"])) for s in stocks_innov]
    value = [score_buffett(s) for s in stocks_value]
    ms = load_morningstar()
    attach_morningstar(innov, ms)
    attach_morningstar(value, ms)
    innov.sort(key=lambda x: -x["score"])
    value.sort(key=lambda x: -x["score"])

    prev_syms = set()
    if previous:
        prev_syms = {p["symbol"] for k in ("innovation", "buffett") for p in previous.get(k, {}).get("picks", [])}

    def section(ranked, salt):
        picks = daily_pick(ranked, day, salt)
        for p in picks:
            p["new_today"] = p["symbol"] not in prev_syms
        ranking = [{**{k: r[k] for k in ("symbol", "name", "score", "price", "currency", "label",
                                         "fair_value", "potential")},
                    "risk": r["risk"]["name"], "risk_level": r["risk"]["level"],
                    "ms_fair_value": (r.get("morningstar") or {}).get("fair_value"),
                    "ms_stars": (r.get("morningstar") or {}).get("stars"),
                    "rules_met": r.get("rules_met")} for r in ranked]
        return {"picks": picks, "ranking": ranking}

    return clean({
        "date": day,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "innovation": section(innov, "innovation"),
        "buffett": section(value, "buffett"),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="nur die ersten N Ticker je Liste (Test)")
    args = ap.parse_args()

    innov_syms = list(INNOVATION)
    value_syms = list(VALUE)
    if args.limit:
        innov_syms, value_syms = innov_syms[: args.limit], value_syms[: args.limit]

    def run(symbols):
        out = []
        for i, sym in enumerate(symbols, 1):
            try:
                d = fetch(sym)
                if d:
                    out.append(d)
                    print(f"[{i}/{len(symbols)}] {sym} ok", flush=True)
                else:
                    print(f"[{i}/{len(symbols)}] {sym} keine Daten", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(symbols)}] {sym} Fehler: {e}", flush=True)
            time.sleep(0.3)
        return out

    stocks_innov = run(innov_syms)
    stocks_value = run(value_syms)
    if len(stocks_innov) + len(stocks_value) < 10:
        sys.exit("Zu wenige Daten geladen – Scan abgebrochen, alte Daten bleiben erhalten.")

    day = dt.date.today().isoformat()
    latest = DATA / "latest.json"
    previous = None
    if latest.exists():
        previous = json.loads(latest.read_text())
        if previous.get("date") == day:  # gleicher Tag neu gescannt -> mit Vortag vergleichen
            hist = sorted((DATA / "history").glob("*.json"))
            hist = [h for h in hist if h.stem < day]
            previous = json.loads(hist[-1].read_text()) if hist else None

    result = build(stocks_innov, stocks_value, day, previous)

    (DATA / "history").mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    latest.write_text(text)
    (DATA / "history" / f"{day}.json").write_text(text)
    dates = sorted((h.stem for h in (DATA / "history").glob("*.json")), reverse=True)
    (DATA / "index.json").write_text(json.dumps({"dates": dates}))
    print(f"Fertig: {len(stocks_innov)} Innovations- und {len(stocks_value)} Value-Aktien bewertet.")


if __name__ == "__main__":
    main()
