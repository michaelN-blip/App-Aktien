"""Bewertungslogik für beide Strategien.

Jede Funktion bekommt ein Kennzahlen-Dict (siehe scan.fetch) und gibt
einen Score von 0-100 plus nachvollziehbare Einzelkriterien zurück.
"""
from __future__ import annotations

DISCOUNT_RATE = 0.10   # Buffett rechnet grob mit 10 % Mindestrendite
TERMINAL_GROWTH = 0.03   # ewiges Wachstum nach Jahr 10 (etwa Inflation)
MAX_GROWTH = 0.15        # Wachstum in Phase 1 (Jahre 1-5) höchstens 15 %


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


ANALYST_WEIGHT = 0.30    # Analysten-Erwartung fließt nur zu 30 % ins Wachstum ein
RATE_BY_RISK = {1: 0.085, 2: 0.09}  # Mindestrendite nach Risikostufe, sonst DISCOUNT_RATE


def is_balance_sheet_business(s):
    """Banken, Versicherer, Vermögensverwalter: Cashflow/ROA/Bruttomarge passen nicht.
    Zahlungsnetzwerke (Visa, Mastercard) und Börsen/Ratingagenturen sind dagegen kapitalarm."""
    if (s.get("sector") or "") != "Financial Services":
        return False
    industry = (s.get("industry") or "").lower()
    return not any(k in industry for k in ("credit services", "financial data", "stock exchange"))


def _dcf(fcf, shares, g, rate=DISCOUNT_RATE):
    """Zwei-Phasen-DCF: Jahre 1-5 mit Wachstum g, Jahre 6-10 flacht es linear auf 3 % ab,
    danach ewig 3 %. Abgezinst mit der Mindestrendite `rate`."""
    total, cf = 0.0, fcf
    for year in range(1, 11):
        gy = g if year <= 5 or g <= TERMINAL_GROWTH else g + (TERMINAL_GROWTH - g) * (year - 5) / 5
        cf *= 1 + gy
        total += cf / (1 + rate) ** year
    terminal = cf * (1 + TERMINAL_GROWTH) / (rate - TERMINAL_GROWTH)
    total += terminal / (1 + rate) ** 10
    return total / shares


def _years(*series):
    """Gemeinsame Jahre mehrerer {Jahr: Wert}-Reihen, aufsteigend."""
    common = set(series[0])
    for x in series[1:]:
        common &= set(x)
    return sorted(common)


def _ups(series):
    """(Anzahl Jahre mit Anstieg, Anzahl Vergleiche) für eine {Jahr: Wert}-Reihe."""
    ys = sorted(series)
    pairs = list(zip(ys, ys[1:]))
    return sum(series[b] > series[a] for a, b in pairs), len(pairs)


def _series_cagr(series):
    ys = sorted(series)
    if len(ys) < 2:
        return None
    first, last = series[ys[0]], series[ys[-1]]
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / (ys[-1] - ys[0])) - 1


def buffett_history(s):
    """Mehrjahres-Kennzahlen aus den Jahresberichten (meist 4 Jahre)."""
    h = s.get("history") or {}
    rev, ni, gp = h.get("revenue", {}), h.get("net_income", {}), h.get("gross_profit", {})
    ocf, capex, da = h.get("operating_cf", {}), h.get("capex", {}), h.get("depreciation", {})
    fcf, assets, eq = h.get("free_cf", {}), h.get("total_assets", {}), h.get("equity", {})
    avg = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731

    roe = {y: ni[y] / eq[y] for y in _years(ni, eq) if eq[y] > 0}
    roa = {y: ni[y] / assets[y] for y in _years(ni, assets) if assets[y] > 0}
    gm = {y: gp[y] / rev[y] for y in _years(gp, rev) if rev[y] > 0}
    nm = {y: ni[y] / rev[y] for y in _years(ni, rev) if rev[y] > 0}

    # Owner Earnings nach Buffett: Gewinn + Abschreibungen - ERHALTUNGS-Investitionen.
    # Erhaltungs-Capex wird (üblich) mit den Abschreibungen angesetzt, höchstens aber mit dem
    # tatsächlichen Capex. Investitionen darüber hinaus sind Wachstum und werden nicht abgezogen.
    oe = {y: ni[y] + da[y] - min(abs(capex[y]), da[y]) for y in _years(ni, da, capex)}
    if not oe:
        oe = {y: ocf[y] + capex[y] for y in _years(ocf, capex)} or dict(fcf)
    # Aktuelle Ertragskraft: Gewinn der letzten 12 Monate, umgerechnet mit dem Owner-Earnings-
    # Verhältnis des letzten Geschäftsjahres. Gedeckelt auf das 1,5-fache des letzten Jahres
    # (Schutz vor Einmaleffekten). Ohne 12-Monats-Zahl: letztes Geschäftsjahr.
    fx = s.get("fx") or 1.0
    oe_norm = None
    if oe:
        last = max(oe)
        oe_last = oe[last]
        oe_norm = oe_last
        ni_ttm = s.get("net_income_ttm")
        if ni_ttm and ni.get(last, 0) > 0 and oe_last > 0:
            ni_ttm_fin = ni_ttm / fx  # net_income_ttm ist schon in Handelswährung
            oe_norm = min(ni_ttm_fin * oe_last / ni[last], 1.5 * oe_last)
        oe_norm *= fx

    rev_up, rev_n = _ups(rev)
    ni_up, ni_n = _ups(ni)
    cash = {y: v for y, v in (fcf or oe).items()}
    return {
        "roe_avg": avg(list(roe.values())), "roe_min": min(roe.values()) if roe else None,
        "roa_avg": avg(list(roa.values())),
        "gross_margin": avg(list(gm.values())) if gm else s.get("gross_margin"),
        "net_margin": avg(list(nm.values())) if nm else s.get("profit_margin"),
        "rev_up": rev_up, "rev_n": rev_n, "rev_cagr": _series_cagr(rev),
        "ni_up": ni_up, "ni_n": ni_n, "ni_cagr": _series_cagr(ni),
        "ni_all_positive": bool(ni) and all(v > 0 for v in ni.values()),
        "ocf_positive": sum(v > 0 for v in ocf.values()), "ocf_n": len(ocf),
        "cash_positive": sum(v > 0 for v in cash.values()), "cash_n": len(cash),
        "oe_norm": oe_norm, "oe_years": len(oe),
    }


def _growth_parts(s, hb=None):
    """(historisches Wachstum, Analysten-Erwartung, gemischtes Wachstum).

    Historie = das kleinere von Umsatz- und Gewinnwachstum der letzten Jahre.
    Analysten = erwartetes Gewinnwachstum nächstes Jahr (Forward- vs. Trailing-EPS).
    Mischung: 70 % Historie + 30 % Analysten, begrenzt auf 0-20 %.
    """
    hb = hb or buffett_history(s)
    candidates = [g for g in (hb["rev_cagr"], hb["ni_cagr"]) if g is not None]
    if not candidates:
        candidates = [g for g in (s.get("earnings_growth"), cagr(s.get("revenue_hist", []))) if g is not None]
    hist = min(candidates) if candidates else 0.03
    hist_c = max(0.0, min(hist, MAX_GROWTH))
    fwd = s.get("forward_growth")
    if fwd is not None:
        # Forward- vs. Trailing-EPS ist durch Sondereffekte verzerrt -> begrenzen:
        # -15 % … +25 % und höchstens 10 Prozentpunkte Abstand zur Historie.
        fwd = max(-0.15, min(fwd, 0.25, hist_c + 0.10))
        fwd = max(fwd, hist_c - 0.10)
    g = hist_c if fwd is None else (1 - ANALYST_WEIGHT) * hist_c + ANALYST_WEIGHT * fwd
    return hist, fwd, max(0.0, min(g, MAX_GROWTH))


def _value_growth(s, hb=None):
    return _growth_parts(s, hb)[2]


def valuation_buffett(s, hb=None):
    """Fairer Wert (pessimistisch / Basis / optimistisch).

    1. Owner Earnings vorhanden -> DCF mit 10 % Mindestrendite, Wachstum halbiert / normal / erhöht.
    2. Banken & Firmen ohne Owner Earnings -> faires KGV (8 + Gewinnwachstum in %, max. 16).
    """
    hb = hb or buffett_history(s)
    shares = s.get("shares")
    oe = hb["oe_norm"] or s.get("free_cashflow")
    hist, fwd, g = _growth_parts(s, hb)
    risk_level = risk_assessment(s)["level"]
    rate = RATE_BY_RISK.get(risk_level, DISCOUNT_RATE)
    growth_txt = f"{pct(g)} Wachstum" + (f" (Historie {pct(hist)}, Analysten {pct(fwd)})" if fwd is not None else "")
    if not is_balance_sheet_business(s) and oe and oe > 0 and shares:
        low = _dcf(oe, shares, g * 0.5, rate)
        base = _dcf(oe, shares, g, rate)
        high = _dcf(oe, shares, min(g * 1.3 + 0.02, 0.25), rate)
        method = (f"DCF auf Owner Earnings ({big(oe)}/Jahr, letzte 12 Monate): {growth_txt} für 5 Jahre, "
                  f"dann abflachend auf 3 %, {pct(rate)} Mindestrendite (Risiko {risk_assessment(s)['name'].lower()})")
        return low, base, high, method
    pe = s.get("pe")
    if pe and pe > 0:
        eps = s["price"] / pe
        g_pct = min(max(hb["ni_cagr"] if hb["ni_cagr"] is not None else (s.get("earnings_growth") or 0.03), 0), 0.08) * 100
        fair_pe = min(8 + g_pct, 16)
        method = f"Faires KGV {fair_pe:.0f} (8 + Gewinnwachstum in %) × Gewinn je Aktie"
        return eps * fair_pe * 0.75, eps * fair_pe, eps * fair_pe * 1.25, method
    return None, None, None, None


def _growth_case(s, growth_mult, margin_mult, exit_pe):
    """5-Jahres-Szenario: Umsatz wächst (abflachend), reife Marge, Bewertung per KGV, abgezinst mit 12 %."""
    rev, shares = s.get("revenue_ttm"), s.get("shares")
    if not rev or not shares:
        return None
    rg = s.get("revenue_growth")
    hist = cagr(s.get("revenue_hist", []))
    g0 = max([x for x in (rg, hist) if x is not None], default=0.10)
    g0 = max(0.0, min(g0 * growth_mult, 1.5))
    for year in range(5):
        rev *= 1 + max(0.06, g0 * 0.75 ** year)
    gm = s.get("gross_margin") or 0.3
    margin = max(0.04, min(gm * 0.4, 0.30)) * margin_mult
    future_equity = rev * margin * exit_pe + (s.get("total_cash") or 0) - (s.get("total_debt") or 0)
    if future_equity <= 0:
        return 0.0
    pm = s.get("profit_margin")
    future_shares = shares * (1.04 ** 5 if pm is not None and pm < 0 else 1.01 ** 5)  # Verwässerung
    return future_equity / future_shares / (1 + GROWTH_DISCOUNT) ** 5


GROWTH_DISCOUNT = 0.12


def valuation_innovation(s):
    low = _growth_case(s, 0.5, 0.7, 15)
    base = _growth_case(s, 1.0, 1.0, 25)
    high = _growth_case(s, 1.3, 1.2, 35)
    method = "5-Jahres-Umsatzmodell mit reifer Gewinnmarge, Exit-KGV 25, 12 % Mindestrendite"
    if _revenue(s) is not None and _revenue(s) < 100e6:
        method += " – bei so wenig Umsatz kaum aussagekräftig (Wert hängt an künftigen Durchbrüchen)"
    return low, base, high, method


def _revenue(s):
    """Umsatz der letzten 12 Monate, sonst letztes Geschäftsjahr; None wenn unbekannt."""
    if s.get("revenue_ttm") is not None:
        return s["revenue_ttm"]
    rev = (s.get("history") or {}).get("revenue") or {}
    return rev[max(rev)] * (s.get("fx") or 1.0) if rev else None


def risk_assessment(s, low=None, high=None):
    """Risikostufe 1-4 aus Schwankung, Verlusten, Schulden, Bewertung, Größe und Unsicherheit."""
    pts, why = 0, []
    beta = s.get("beta")
    if beta and beta > 2:
        pts += 2; why.append(f"sehr volatil (Beta {beta:.1f})")
    elif beta and beta > 1.3:
        pts += 1; why.append(f"schwankungsfreudig (Beta {beta:.1f})")
    hi, price = s.get("fifty_two_high"), s["price"]
    if hi and price < hi * 0.5:
        pts += 2; why.append("über 50 % unter dem Jahreshoch")
    elif hi and price < hi * 0.7:
        pts += 1; why.append("über 30 % unter dem Jahreshoch")
    pm = s.get("profit_margin")
    if pm is not None and pm < 0:
        pts += 2; why.append("macht Verluste")
    elif pm is not None and pm < 0.05:
        pts += 1; why.append("geringe Gewinnmarge")
    de = s.get("debt_to_equity")
    if not is_balance_sheet_business(s) and de is not None and (de > 2 or de < 0):
        pts += 1; why.append("hohe Verschuldung")
    if (s.get("total_cash") or 0) < (s.get("total_debt") or 0) and pm is not None and pm < 0:
        pts += 1; why.append("mehr Schulden als Cash bei Verlusten")
    ps, pe = s.get("ps"), s.get("pe")
    if (ps and ps > 20) or (pe and pe > 50):
        pts += 1; why.append("sehr hohe Bewertung")
    if _revenue(s) is not None and _revenue(s) < 100e6:
        pts += 2; why.append("kaum Umsatz – Geschäftsmodell noch unbewiesen")
    fwd = s.get("forward_growth")
    if fwd is not None and fwd < -0.05:
        pts += 1; why.append(f"Analysten erwarten Gewinnrückgang ({pct(fwd)})")
    mc = s.get("market_cap") or 0
    if mc < 2e9:
        pts += 2; why.append("kleines Unternehmen")
    elif mc < 10e9:
        pts += 1; why.append("mittelgroßes Unternehmen")
    if low is not None and high and low > 0 and high / low > 4:
        pts += 1; why.append("Wert schwer zu schätzen (große Spanne)")
    elif low is not None and high and low <= 0:
        pts += 1; why.append("Wert schwer zu schätzen (große Spanne)")
    level = 1 if pts <= 1 else 2 if pts <= 3 else 3 if pts <= 5 else 4
    name = {1: "Niedrig", 2: "Mittel", 3: "Hoch", 4: "Sehr hoch"}[level]
    return {"level": level, "name": name, "points": pts, "factors": why}


def _valuation_fields(s, low, base, high, method):
    price = s["price"]
    if base is None:
        return {"fair_value": None, "fair_low": None, "fair_high": None, "potential": None,
                "potential_low": None, "potential_high": None, "valuation_method": None,
                "risk": risk_assessment(s)}
    return {
        "fair_value": base, "fair_low": low, "fair_high": high, "valuation_method": method,
        "potential": base / price - 1,
        "potential_low": low / price - 1 if low is not None else None,
        "potential_high": high / price - 1 if high is not None else None,
        "risk": risk_assessment(s, low, high),
    }


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
    is_financial = is_balance_sheet_business(s)
    hb = buffett_history(s)
    rules = []  # Buffett-Mindestkriterien (erfüllt ja/nein)

    # 1. Eigenkapitalrendite im Schnitt >= 15 %
    roe = hb["roe_avg"] if hb["roe_avg"] is not None else s.get("roe")
    p = tiers(roe, [(0.20, 12), (0.15, 9), (0.10, 3)])
    if p and hb["roe_min"] is not None and hb["roe_min"] < 0.10:
        p -= 3  # nicht stetig
    c.append(crit("Eigenkapitalrendite Ø", pct(roe), p, 12, f"Mindestens 15 % (schwächstes Jahr {pct(hb['roe_min'])})"))
    rules.append(("Eigenkapitalrendite Ø ≥ 15 %", roe is not None and roe >= 0.15))
    if roe and roe >= 0.15:
        reasons.append(f"Eigenkapitalrendite im Schnitt {pct(roe)} – Zeichen für einen Burggraben")

    # 2. Gesamtkapitalrendite im Schnitt >= 10 %
    roa = hb["roa_avg"]
    if is_financial:
        p, shown = 5, f"{pct(roa, 1)} (Bank/Versicherung)"
        rules.append(("Gesamtkapitalrendite Ø ≥ 10 %", None))
    else:
        p, shown = tiers(roa, [(0.10, 10), (0.07, 5), (0.05, 2)]), pct(roa, 1)
        rules.append(("Gesamtkapitalrendite Ø ≥ 10 %", roa is not None and roa >= 0.10))
    c.append(crit("Gesamtkapitalrendite Ø (ROA)", shown, p, 10, "Mindestens 10 % – Gewinn im Verhältnis zum ganzen Vermögen"))
    if not is_financial and roa and roa >= 0.10:
        reasons.append(f"Gesamtkapitalrendite im Schnitt {pct(roa)} – arbeitet mit wenig Kapital sehr profitabel")

    # 3. Bruttomarge
    gm = hb["gross_margin"]
    if is_financial and gm is None:
        p, shown = 4, "Bank/Versicherung"
        rules.append(("Bruttomarge ≥ 40 %", None))
    else:
        p, shown = tiers(gm, [(0.40, 8), (0.30, 4), (0.20, 1)]), pct(gm)
        rules.append(("Bruttomarge ≥ 40 %", gm is not None and gm >= 0.40))
    c.append(crit("Bruttomarge Ø", shown, p, 8, "Mindestens 40 % – Preissetzungsmacht"))

    # 4. Nettomarge
    nm = hb["net_margin"]
    p = tiers(nm, [(0.20, 8), (0.15, 6), (0.10, 3)])
    c.append(crit("Nettomarge Ø", pct(nm), p, 8, "Mindestens 15 % bleiben als Gewinn übrig"))
    rules.append(("Nettomarge Ø ≥ 15 %", nm is not None and nm >= 0.15))
    if gm and gm >= 0.40 and nm and nm >= 0.15:
        reasons.append(f"Gute Margen: brutto {pct(gm)}, netto {pct(nm)}")

    # 5. Stetiges Umsatzwachstum
    up, n = hb["rev_up"], hb["rev_n"]
    p = 0
    if n:
        p = 10 if up == n else 5 if up == n - 1 and (hb["rev_cagr"] or 0) > 0 else 0
    c.append(crit("Stetiges Umsatzwachstum", f"{up}/{n} Jahre gestiegen · {pct(hb['rev_cagr'], 1)} p. a." if n else "–",
                  p, 10, "Umsatz steigt Jahr für Jahr"))
    rules.append(("Umsatz stetig wachsend", bool(n) and up >= n - 1 and (hb["rev_cagr"] or 0) > 0))
    if n and up == n:
        reasons.append(f"Umsatz in jedem der letzten {n} Jahre gestiegen ({pct(hb['rev_cagr'], 1)} p. a.)")
    elif n and (hb["rev_cagr"] or 0) <= 0:
        risks.append("Umsatz wächst nicht")

    # 6. Gewinnwachstum
    up, n = hb["ni_up"], hb["ni_n"]
    p = 0
    if n and hb["ni_all_positive"]:
        p = 10 if up == n else 6 if (hb["ni_cagr"] or 0) > 0 else 2
    c.append(crit("Gewinnwachstum", f"{up}/{n} Jahre gestiegen · {pct(hb['ni_cagr'], 1)} p. a." if n else "–",
                  p, 10, "Jedes Jahr Gewinn, Tendenz steigend"))
    rules.append(("Gewinn wachsend", hb["ni_all_positive"] and (hb["ni_cagr"] or 0) > 0))
    if p == 10:
        reasons.append(f"Gewinn in jedem der letzten {n} Jahre gestiegen ({pct(hb['ni_cagr'], 1)} p. a.)")
    elif n and not hb["ni_all_positive"]:
        risks.append("In mindestens einem der letzten Jahre Verlust gemacht")
    elif n and (hb["ni_cagr"] or 0) <= 0:
        risks.append("Gewinn ist in den letzten Jahren gesunken")

    # 7. Immer guter Cashflow
    cp, cn = hb["cash_positive"], hb["cash_n"]
    p = 10 if cn and cp == cn else 5 if hb["ocf_n"] and hb["ocf_positive"] == hb["ocf_n"] else 0
    if is_financial and not cn:
        p = 5
    c.append(crit("Cashflow stets positiv", f"{cp}/{cn} Jahre positiv" if cn else "–", p, 10,
                  "Free Cashflow / Owner Earnings in jedem Jahr positiv"))
    rules.append(("Cashflow jedes Jahr positiv", (cn > 0 and cp == cn) if not is_financial else None))
    if cn and cp == cn and not is_financial:
        reasons.append(f"In allen {cn} Jahren positiver Free Cashflow")

    # 8. Wenig Schulden
    de = s.get("debt_to_equity")
    if is_financial:
        p, shown = 3, "Bank/Versicherung"
    else:
        p = tiers(de, [(0.5, 5), (1.0, 3), (2.0, 1)], higher_is_better=False) if de is not None and de >= 0 else 0
        shown = num(de, 2)
        if de is not None and (de > 2 or de < 0):
            risks.append("Hohe Verschuldung bzw. negatives Eigenkapital")
    c.append(crit("Verschuldung (Debt/Equity)", shown, p, 5, "Ideal < 0,5"))

    # 9. KGV nicht zu hoch
    pe = s.get("pe")
    p = tiers(pe, [(15, 10), (20, 7), (25, 4), (30, 1)], higher_is_better=False) if pe and pe > 0 else 0
    c.append(crit("KGV", num(pe), p, 10, "Ideal ≤ 15, höchstens 25"))
    rules.append(("KGV ≤ 25", pe is not None and 0 < pe <= 25))
    if pe and 0 < pe <= 15:
        reasons.append(f"Günstiges KGV von {num(pe)}")
    elif pe and pe > 25:
        risks.append(f"KGV von {num(pe)} ist für Buffett zu hoch")

    # 10. Owner Earnings & Sicherheitsmarge
    low, iv, high, method = valuation_buffett(s, hb)
    price = s["price"]
    mos = (iv - price) / iv if iv and iv > 0 else None
    oe = hb["oe_norm"]
    oe_yield = oe / s["market_cap"] if oe and s.get("market_cap") else None
    p = tiers(mos, [(0.30, 17), (0.15, 13), (0.0, 8), (-0.20, 3)])
    gap = iv / price - 1 if iv and iv > 0 else None
    shown = "–" if gap is None else f"Kurs {pct(abs(gap))} {'unter' if gap >= 0 else 'über'} innerem Wert"
    c.append(crit("Sicherheitsmarge (Owner Earnings)", shown, p, 17,
                  f"Owner-Earnings-Rendite {pct(oe_yield, 1)} · innerer Wert ≈ {iv:.2f} {s['currency']}" if iv
                  else "Kurs unter dem inneren Wert"))
    rules.append(("Kurs unter innerem Wert", mos is not None and mos >= 0))
    if mos is not None and mos >= 0.15:
        reasons.append(f"Sicherheitsmarge von {pct(mos)}: Kurs liegt klar unter dem inneren Wert")
    elif mos is not None and mos < -0.20:
        risks.append(f"Deutlich über dem geschätzten inneren Wert ({iv:.0f} {s['currency']})")
    if oe_yield and oe_yield >= 0.05:
        reasons.append(f"Owner-Earnings-Rendite von {pct(oe_yield, 1)} – wie eine Anleihe mit wachsendem Kupon")

    dy = s.get("dividend_yield")  # Anteil, z. B. 0.03 = 3 %
    if dy and dy >= 0.02:
        reasons.append(f"Zahlt {pct(dy, 1)} Dividende")

    checked = [ok for _, ok in rules if ok is not None]
    met = sum(checked)
    score = sum(x["points"] for x in c)
    label = ("Starker Buffett-Kandidat" if score >= 75 else "Interessant" if score >= 60
             else "Beobachten" if score >= 45 else "Eher nicht")
    too_expensive = (pe is not None and pe > 30) or (mos is not None and mos < -0.30)
    if too_expensive and score >= 45:
        label = "Top-Firma, aber zu teuer"
    extra = {
        **_valuation_fields(s, low, iv, high, method),
        "intrinsic_value": iv, "margin_of_safety": mos, "owner_earnings": oe, "owner_earnings_yield": oe_yield,
        "rules": [{"name": n, "ok": ok} for n, ok in rules], "rules_met": f"{met}/{len(checked)}",
        "metrics": {"KGV": num(pe), "ROE Ø": pct(roe), "ROA Ø": pct(hb["roa_avg"]),
                    "Bruttomarge": pct(gm), "Nettomarge": pct(nm), "Owner Earn. Rendite": pct(oe_yield, 1)},
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
        risks.append("Mehr als 50 % unter dem 52-Wochen-Hoch – hohe Schwankungen")
    beta = s.get("beta")
    if beta and beta > 2:
        risks.append(f"Sehr volatil (Beta {num(beta)})")
    risks.append("Spekulativ: Totalverlust möglich – nur kleine Positionen")

    score = sum(x["points"] for x in c)
    label = ("Hohes Potenzial" if score >= 70 else "Spannend" if score >= 55
             else "Beobachten" if score >= 40 else "Noch zu früh/zu teuer")
    extra = {
        **_valuation_fields(s, *valuation_innovation(s)),
        "theme": theme, "upside": up,
        "metrics": {"Umsatzwachstum": pct(growth), "Bruttomarge": pct(gm), "KUV": num(ps),
                    "Marktkap.": big(mc), "Insider": pct(ins, 1), "Kursziel": num(tp, 2)},
    }
    return _result(s, score, c, reasons, risks, label, extra)


# ---------------------------------------------------------- Einstufung ---

def classify(s, b, i, theme=None):
    """Aktien-Typ (Value, Growth, Qualität …), Zusatz-Merkmale und welche Strategie passt.

    b = score_buffett(s), i = score_innovation(s, theme)
    """
    hb = buffett_history(s)
    growth = max([x for x in (s.get("revenue_growth"), hb["rev_cagr"]) if x is not None], default=None)
    pe, pm, rev = s.get("pe"), s.get("profit_margin"), _revenue(s)
    met, total = (int(x) for x in b["rules_met"].split("/")) if b.get("rules_met") else (0, 1)

    if (rev is not None and rev < 100e6) or (pm is not None and pm < 0 and (growth or 0) >= 0.15):
        style, why = "Spekulativ / Frühphase", "macht noch Verluste oder kaum Umsatz – setzt auf künftige Durchbrüche"
    elif total and met / total >= 0.7 and growth is not None and growth >= 0.15:
        style, why = "Qualitäts-Wachstum", (f"erfüllt {b['rules_met']} Buffett-Kriterien und wächst trotzdem um "
                                             f"{pct(growth)} pro Jahr – seltene Kombination")
    elif total and met / total >= 0.7:
        style, why = "Qualität (Buffett-Typ)", f"erfüllt {b['rules_met']} Buffett-Kriterien – stabiler, profitabler Burggraben"
    elif growth is not None and growth >= 0.20:
        style, why = "Growth (Wachstum)", f"wächst den Umsatz um {pct(growth)} pro Jahr"
    elif pe is not None and 0 < pe <= 15:
        style, why = "Value (günstig)", f"niedriges KGV von {num(pe)}"
    elif pm is not None and pm < 0:
        style, why = "Turnaround / Verlust", "macht Verluste ohne starkes Wachstum"
    else:
        style, why = "Standardwert (gemischt)", "weder klarer Wachstums- noch klarer Value-Wert"

    tags = []
    mc = s.get("market_cap") or 0
    tags.append("Large Cap" if mc >= 10e9 else "Mid Cap" if mc >= 2e9 else "Small Cap")
    dy = s.get("dividend_yield")  # Anteil
    if dy and dy >= 0.025:
        tags.append(f"Dividende {pct(dy, 1)}")
    sector, industry = s.get("sector") or "", (s.get("industry") or "").lower()
    if sector in ("Energy", "Basic Materials") or "semiconductor equipment" in industry or "auto" in industry:
        tags.append("Zyklisch")
    if sector in ("Consumer Defensive", "Utilities") or "insurance" in industry:
        tags.append("Defensiv")
    if theme:
        tags.append(theme)
    if (s.get("beta") or 0) > 1.8:
        tags.append("Hohe Schwankung")

    primary = "innovation" if style in ("Spekulativ / Frühphase", "Growth (Wachstum)") else "buffett"
    main = i if primary == "innovation" else b
    fits = []
    if b["score"] >= 60 and b["label"] != "Top-Firma, aber zu teuer":
        fits.append("Buffett-Value")
    if i["score"] >= 55:
        fits.append("Innovation / Vervielfacher")

    pot = main.get("potential")
    risk = main.get("risk") or {}
    verdict = (f"Einstufung: {style} – {why}. "
               f"Buffett-Score {b['score']}/100 ({b['label']}), Innovations-Score {i['score']}/100 ({i['label']}). ")
    if main.get("fair_value"):
        verdict += (f"Geschätzter fairer Wert ≈ {main['fair_value']:.2f} {s['currency']} "
                    f"({'+' if pot >= 0 else '−'}{abs(pot) * 100:.0f} % zum Kurs). ")
    verdict += f"Risiko: {risk.get('name', '–')}."
    return {"style": style, "style_reason": why, "tags": tags, "primary": primary,
            "fits": fits, "verdict": verdict}
