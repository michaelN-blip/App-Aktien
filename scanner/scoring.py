"""Bewertungslogik für beide Strategien.

Jede Funktion bekommt ein Kennzahlen-Dict (siehe scan.fetch) und gibt
einen Score von 0-100 plus nachvollziehbare Einzelkriterien zurück.
"""
from __future__ import annotations

DISCOUNT_RATE = 0.10   # Buffett rechnet grob mit 10 % Mindestrendite
TERMINAL_GROWTH = 0.025
MAX_GROWTH = 0.12


def pct(x, digits=0):
    return "–" if x is None else f"{x * 100:.{digits}f} %"


def num(x, digits=1):
    return "–" if x is None else f"{x:.{digits}f}"


def big(x):
    if x is None:
        return "–"
    for div, unit in ((1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio.")):
        if abs(x) >= div:
            return f"{x / div:.1f} {unit}"
    return f"{x:.0f}"


def tiers(value, steps, higher_is_better=True):
    """steps: [(Schwelle, Punkte), ...] von bester zu schlechtester Stufe."""
    if value is None:
        return 0
    for threshold, pts in steps:
        if (value >= threshold) if higher_is_better else (value < threshold):
            return pts
    return 0


def cagr(hist):
    """Jährliche Wachstumsrate aus einer Liste (neueste zuerst)."""
    vals = [v for v in hist if v is not None]
    if len(vals) < 2 or vals[-1] <= 0 or vals[0] <= 0:
        return None
    return (vals[0] / vals[-1]) ** (1 / (len(vals) - 1)) - 1


def intrinsic_value(s):
    """Vereinfachte DCF auf Basis des Free Cashflows ("Owner Earnings")."""
    fcf, shares = s.get("free_cashflow"), s.get("shares")
    if not fcf or fcf <= 0 or not shares:
        return None, None
    candidates = [g for g in (s.get("earnings_growth"), cagr(s.get("revenue_hist", []))) if g is not None]
    g = min(candidates) if candidates else 0.03
    g = max(0.0, min(g, MAX_GROWTH))
    total, cf = 0.0, fcf
    for year in range(1, 11):
        cf *= 1 + g
        total += cf / (1 + DISCOUNT_RATE) ** year
    terminal = cf * (1 + TERMINAL_GROWTH) / (DISCOUNT_RATE - TERMINAL_GROWTH)
    total += terminal / (1 + DISCOUNT_RATE) ** 10
    return total / shares, g


def _result(s, score, criteria, reasons, risks, label, extra):
    base = {k: s.get(k) for k in ("symbol", "name", "sector", "industry", "country", "currency",
                                  "price", "market_cap", "summary")}
    base.update(score=round(score), label=label, criteria=criteria, reasons=reasons, risks=risks, **extra)
    return base


def crit(name, shown, pts, max_pts, hint):
    return {"name": name, "value": shown, "points": pts, "max": max_pts, "hint": hint}


# ---------------------------------------------------------------- Buffett ---

def score_buffett(s):
    c, reasons, risks = [], [], []
    is_financial = (s.get("sector") or "") == "Financial Services"

    # 1. Hohe Eigenkapitalrendite = Burggraben
    roe = s.get("roe")
    p = tiers(roe, [(0.20, 20), (0.15, 15), (0.10, 7)])
    c.append(crit("Eigenkapitalrendite (ROE)", pct(roe), p, 20, "Buffett will dauerhaft > 15 %"))
    if roe and roe >= 0.15:
        reasons.append(f"Hohe Eigenkapitalrendite von {pct(roe)} – Zeichen für einen Burggraben")

    # 2. Wenig Schulden
    de = s.get("debt_to_equity")
    if is_financial:
        p = 8
        shown = "Bank/Versicherung"
    else:
        p = tiers(de, [(0.5, 15), (1.0, 8), (2.0, 3)], higher_is_better=False) if de is not None and de >= 0 else 0
        shown = num(de, 2)
    c.append(crit("Verschuldung (Debt/Equity)", shown, p, 15, "Ideal < 0,5"))
    if not is_financial and de is not None and 0 <= de < 0.5:
        reasons.append("Solide Bilanz mit wenig Schulden")
    if not is_financial and de is not None and (de > 2 or de < 0):
        risks.append("Hohe Verschuldung bzw. negatives Eigenkapital")

    # 3. Preissetzungsmacht
    om = s.get("operating_margin")
    p = tiers(om, [(0.20, 15), (0.12, 8), (0.06, 3)])
    c.append(crit("Operative Marge", pct(om), p, 15, "Hohe Margen = Preissetzungsmacht"))
    if om and om >= 0.20:
        reasons.append(f"Starke Preissetzungsmacht (operative Marge {pct(om)})")

    # 4. Beständige Gewinne
    ni = s.get("net_income_hist") or []
    p = 0
    if ni and all(v > 0 for v in ni):
        p += 10
        if len(ni) >= 2 and ni[0] > ni[-1]:
            p += 5
    c.append(crit("Gewinn-Beständigkeit", f"{sum(v > 0 for v in ni)}/{len(ni)} Jahre Gewinn" if ni else "–",
                  p, 15, "Jedes Jahr profitabel und wachsend"))
    if p == 15:
        reasons.append(f"In allen {len(ni)} letzten Geschäftsjahren profitabel und mit Gewinnwachstum")
    elif ni and ni[0] < ni[-1]:
        risks.append("Gewinn ist in den letzten Jahren gesunken")

    # 5. Cash-Maschine
    fcf, rev = s.get("free_cashflow"), s.get("revenue_ttm")
    fcf_margin = fcf / rev if fcf and rev else None
    p = 10 if fcf_margin and fcf_margin >= 0.10 else 5 if fcf and fcf > 0 else 0
    c.append(crit("Free-Cashflow-Marge", pct(fcf_margin), p, 10, "Echtes Geld, nicht nur Buchgewinn"))

    # 6. Preis vs. innerer Wert (Sicherheitsmarge)
    iv, g = (None, None) if is_financial else intrinsic_value(s)
    price = s["price"]
    mos = (iv - price) / iv if iv else None
    if mos is not None:
        p = tiers(mos, [(0.30, 25), (0.15, 18), (0.0, 10), (-0.20, 4)])
        c.append(crit("Sicherheitsmarge (DCF)", pct(mos), p, 25,
                      f"Innerer Wert ≈ {iv:.2f} {s['currency']} bei {pct(g)} Wachstum"))
        if mos >= 0.15:
            reasons.append(f"Notiert {pct(mos)} unter dem geschätzten inneren Wert")
        elif mos < -0.20:
            risks.append(f"Aktuell deutlich über dem geschätzten inneren Wert ({iv:.0f} {s['currency']})")
    else:
        pe, pb = s.get("pe"), s.get("pb")
        p = tiers(pe, [(12, 15), (16, 10), (22, 5)], higher_is_better=False) if pe and pe > 0 else 0
        if is_financial and pb:
            p += tiers(pb, [(1.2, 10), (2.0, 5)], higher_is_better=False)
        c.append(crit("Bewertung (KGV/KBV)", f"KGV {num(pe)} · KBV {num(pb)}", p, 25, "Günstig im Verhältnis zum Gewinn"))
        if pe and 0 < pe < 15:
            reasons.append(f"Günstiges KGV von {num(pe)}")

    pe = s.get("pe")
    if pe and pe > 35:
        risks.append(f"Hohes KGV von {num(pe)} – wenig Spielraum für Enttäuschungen")
    if s.get("dividend_yield"):
        dy = s["dividend_yield"]
        dy = dy / 100 if dy > 1 else dy  # yfinance liefert je nach Version % oder Anteil
        if dy >= 0.02:
            reasons.append(f"Zahlt {pct(dy, 1)} Dividende")

    score = sum(x["points"] for x in c)
    label = ("Starker Buffett-Kandidat" if score >= 75 else "Interessant" if score >= 60
             else "Beobachten" if score >= 45 else "Eher nicht")
    extra = {
        "intrinsic_value": iv, "margin_of_safety": mos, "growth_assumption": g,
        "metrics": {"KGV": num(pe), "Forward-KGV": num(s.get("forward_pe")), "ROE": pct(roe),
                    "Op. Marge": pct(om), "Debt/Equity": num(de, 2), "Marktkap.": big(s.get("market_cap"))},
    }
    return _result(s, score, c, reasons, risks, label, extra)


# ------------------------------------------------------------- Innovation ---

def score_innovation(s, theme=None):
    c, reasons, risks = [], [], []

    # 1. Umsatzwachstum
    rg = s.get("revenue_growth")
    hist_g = cagr(s.get("revenue_hist", []))
    growth = max([x for x in (rg, hist_g) if x is not None], default=None)
    p = tiers(growth, [(0.50, 25), (0.30, 18), (0.15, 10), (0.05, 4)])
    c.append(crit("Umsatzwachstum", pct(growth), p, 25, "Ein Vervielfacher wächst > 30 % pro Jahr"))
    if growth and growth >= 0.30:
        reasons.append(f"Wächst den Umsatz um {pct(growth)} pro Jahr")

    # 2. Bruttomarge = skalierbares Geschäftsmodell
    gm = s.get("gross_margin")
    p = tiers(gm, [(0.60, 15), (0.40, 9), (0.25, 4)])
    c.append(crit("Bruttomarge", pct(gm), p, 15, "Hoch = skalierbar (Software-ähnlich)"))
    if gm and gm >= 0.60:
        reasons.append(f"Skalierbares Geschäftsmodell (Bruttomarge {pct(gm)})")

    # 3. Klein genug, um sich zu vervielfachen
    mc = s.get("market_cap")
    p = tiers(mc, [(5e9, 15), (20e9, 12), (75e9, 7), (300e9, 3)], higher_is_better=False)
    c.append(crit("Größe / Luft nach oben", big(mc), p, 15, "100-Bagger starten klein"))
    if mc and mc < 20e9:
        reasons.append(f"Noch klein (Marktkap. {big(mc)}) – viel Raum zum Wachsen")

    # 4. Gründer/Insider an Bord
    ins = s.get("insider_pct")
    p = tiers(ins, [(0.10, 10), (0.03, 5), (0.01, 2)])
    c.append(crit("Insider-Anteil", pct(ins, 1), p, 10, "Gründergeführt = Skin in the Game"))
    if ins and ins >= 0.10:
        reasons.append(f"Insider halten {pct(ins)} – Management zieht mit den Aktionären an einem Strang")

    # 5. Finanzielle Ausdauer
    cash, debt = s.get("total_cash"), s.get("total_debt") or 0
    p = 10 if cash and cash > debt else 4 if cash and cash > debt * 0.5 else 0
    c.append(crit("Cash vs. Schulden", f"{big(cash)} / {big(debt)}", p, 10, "Genug Geld, um durchzuhalten"))
    if p == 0:
        risks.append("Mehr Schulden als Cash – evtl. Kapitalerhöhungen nötig (Verwässerung)")

    # 6. Investition in Innovation
    rnd, rev = s.get("rnd_latest"), s.get("revenue_latest")
    ri = rnd / rev if rnd and rev else None
    p = tiers(ri, [(0.15, 10), (0.08, 5), (0.03, 2)])
    c.append(crit("F&E-Quote", pct(ri), p, 10, "Anteil des Umsatzes für Forschung"))

    # 7. Analysten-Kursziel
    tp, price = s.get("target_price"), s["price"]
    up = tp / price - 1 if tp else None
    p = tiers(up, [(0.30, 10), (0.10, 5)])
    c.append(crit("Analysten-Kursziel", pct(up), p, 10, "Potenzial bis zum mittleren Kursziel"))

    # 8. Momentum
    ma = s.get("ma200")
    p = 5 if ma and price > ma else 0
    c.append(crit("Trend (über 200-Tage-Linie)", "ja" if p else "nein", p, 5, "Markt erkennt die Story"))

    # Risiken
    pm = s.get("profit_margin")
    if pm is not None and pm < 0:
        risks.append(f"Noch nicht profitabel (Nettomarge {pct(pm)})")
    ps = s.get("ps")
    if ps and ps > 30:
        risks.append(f"Sehr hoch bewertet: {num(ps, 0)}-facher Umsatz")
    hi = s.get("fifty_two_high")
    if hi and price < hi * 0.5:
        risks.append(f"Mehr als 50 % unter dem 52-Wochen-Hoch – hohe Schwankungen")
    beta = s.get("beta")
    if beta and beta > 2:
        risks.append(f"Sehr volatil (Beta {num(beta)})")
    risks.append("Spekulativ: Totalverlust möglich – nur kleine Positionen")

    score = sum(x["points"] for x in c)
    label = ("Hohes Potenzial" if score >= 70 else "Spannend" if score >= 55
             else "Beobachten" if score >= 40 else "Noch zu früh/zu teuer")
    extra = {
        "theme": theme, "upside": up,
        "metrics": {"Umsatzwachstum": pct(growth), "Bruttomarge": pct(gm), "KUV": num(ps),
                    "Marktkap.": big(mc), "Insider": pct(ins, 1), "Kursziel": num(tp, 2)},
    }
    return _result(s, score, c, reasons, risks, label, extra)
