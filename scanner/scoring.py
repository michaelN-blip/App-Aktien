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
        if ni and last < max(ni):  # Owner Earnings nur aus veralteten Jahren -> letzter Free Cashflow
            oe_last = max(oe_last, (fcf or {}).get(max(ni), oe_last))
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
                  f"dann abflachend auf 3 %, {pct(rate, 1)} Mindestrendite (Risiko {risk_assessment(s)['name'].lower()})")
        return low, base, high, method
    pe = s.get("pe")
    if pe and pe > 0:
        eps = s["price"] / pe
        g_pct = min(max(hb["ni_cagr"] if hb["ni_cagr"] is not None else (s.get("earnings_growth") or 0.03), 0), 0.08) * 100
        fair_pe = min(8 + g_pct, 16)
        method = f"Faires KGV {fair_pe:.0f} (8 + Gewinnwachstum in %) × Gewinn je Aktie"
        return eps * fair_pe * 0.75, eps * fair_pe, eps * fair_pe * 1.25, method
    return None, None, None, None


def _growth_case(s, growth_mult, margin_mult, exit_pe, decay=0.65, cap=1.0):
    """5-Jahres-Szenario: Umsatz wächst (abflachend mit Faktor `decay` pro Jahr), reife Marge,
    Bewertung per KGV, abgezinst mit 12 %."""
    rev, shares = s.get("revenue_ttm"), s.get("shares")
    if not rev or not shares:
        return None
    rg = s.get("revenue_growth")
    hist = cagr(s.get("revenue_hist", []))
    g0 = max([x for x in (rg, hist) if x is not None], default=0.10)
    # Startwachstum begrenzt (pessimistisch 20 %, Basis 80 %, optimistisch 100 %), flacht jährlich ab
    g0 = max(0.0, min(g0 * growth_mult, cap))
    for year in range(5):
        rev *= 1 + max(0.06 if cap > 0.2 else 0.02, g0 * decay ** year)
    gm = s.get("gross_margin") or 0.3
    margin = max(0.03, min(gm * 0.35, 0.25)) * margin_mult
    pm = s.get("profit_margin")
    if pm is not None and pm < 0:
        margin *= 0.75  # Verlustfirmen: reife Marge ist unsicherer
    future_equity = rev * margin * exit_pe + (s.get("total_cash") or 0) - (s.get("total_debt") or 0)
    if future_equity <= 0:
        return 0.0
    future_shares = shares * (1.04 ** 5 if pm is not None and pm < 0 else 1.01 ** 5)  # Verwässerung
    return future_equity / future_shares / (1 + GROWTH_DISCOUNT) ** 5


GROWTH_DISCOUNT = 0.12


DECAY_BY_CHANCE = {"Hoch": 0.72, "Mittel": 0.65, "Niedrig": 0.58}  # wie lange das Wachstum anhält
MIN_REVENUE_FOR_MODEL = 50e6


def bagger_multiple(s, growth_mult, margin_mult, exit_pe, floor, decay=0.7, cap=1.0):
    """Vervielfachung in 10 Jahren: Börsenwert-Szenario in 10 Jahren je Aktie / heutiger Kurs (nicht abgezinst)."""
    rev, shares = s.get("revenue_ttm"), s.get("shares")
    if not rev or not shares or not s.get("price"):
        return None
    g0 = max([x for x in (s.get("revenue_growth"), cagr(s.get("revenue_hist", []))) if x is not None], default=0.10)
    g0 = max(0.0, min(g0 * growth_mult, cap))
    for year in range(10):
        rev *= 1 + max(floor, g0 * decay ** year)
    gm = s.get("gross_margin") or 0.3
    margin = max(0.03, min(gm * 0.35, 0.25)) * margin_mult
    pm = s.get("profit_margin")
    if pm is not None and pm < 0:
        margin *= 0.75
    equity = rev * margin * exit_pe + (s.get("total_cash") or 0) - (s.get("total_debt") or 0)
    future_shares = shares * (1.03 ** 10 if pm is not None and pm < 0 else 1.01 ** 10)
    return max(equity, 0) / future_shares / s["price"]


def valuation_innovation(s, chance="Mittel"):
    """Wachstumsbasierter fairer Wert. Die Wachstumschance bestimmt, wie lange das Wachstum anhält."""
    rev = _revenue(s)
    if rev is not None and rev < MIN_REVENUE_FOR_MODEL:
        return None, None, None, (f"Nicht berechenbar: erst {big(rev)} Umsatz – der Wert hängt allein an künftigen "
                                  "Durchbrüchen (Produkt, Zulassung, Aufträge). Reine Wette auf die Innovation.")
    d = DECAY_BY_CHANCE.get(chance, 0.65)
    low = _growth_case(s, 0.5, 0.5, 12, d - 0.10, cap=0.20)   # Wachstum stockt, Marge halb so hoch
    base = _growth_case(s, 1.0, 1.0, 25, d, cap=0.80)
    high = _growth_case(s, 1.4, 1.3, 40, d + 0.03, cap=1.0)
    method = (f"Wachstumsmodell: Umsatz 5 Jahre (Start max. 100 %), Wachstumschance {chance.lower()} → "
              f"Wachstum flacht {'langsam' if chance == 'Hoch' else 'schnell' if chance == 'Niedrig' else 'mittel'} ab; "
              "reife Gewinnmarge, Exit-KGV 25 (optimistisch 40; pessimistisch 12 bei stockendem Wachstum und halber Marge), "
              "12 % Mindestrendite")
    if rev is not None and rev < 200e6:
        method += " – bei noch kleinem Umsatz sehr unsicher"
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
                "potential_low": None, "potential_high": None, "valuation_method": method,
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
    """100-Bagger-Score nach Christopher Mayer ("100 Baggers"): Wachstum, Größe, Skalierbarkeit,
    Gründer, Innovation, Weg zur Profitabilität, vernünftiger Startpreis – keine Cashflow-Kennzahlen."""
    c, reasons, risks = [], [], []
    h = s.get("history") or {}
    rev_hist, ni_hist = h.get("revenue") or {}, h.get("net_income") or {}
    price = s["price"]

    # 1. Wachstumstempo
    rg = s.get("revenue_growth")
    hist_g = _series_cagr(rev_hist) if rev_hist else cagr(s.get("revenue_hist", []))
    growth = rg if rg is not None else hist_g
    p = tiers(growth, [(0.50, 20), (0.30, 15), (0.20, 10), (0.10, 4)])
    c.append(crit("Wachstumstempo", pct(growth), p, 20, "Umsatzwachstum – ein Vervielfacher wächst > 30 % pro Jahr"))
    if growth and growth >= 0.30:
        reasons.append(f"Wächst den Umsatz um {pct(growth)} pro Jahr")

    # 2. Beständigkeit / Beschleunigung
    up, n = _ups(rev_hist)
    p = (7 if n and up == n else 4 if n and up >= n - 1 else 0)
    accel = growth is not None and hist_g is not None and growth > hist_g + 0.02
    if accel:
        p += 3
    shown = (f"{up}/{n} Jahre gestiegen" if n else "–") + (" · beschleunigt" if accel else "")
    c.append(crit("Wachstums-Beständigkeit", shown, p, 10, "Jedes Jahr mehr Umsatz, idealerweise schneller werdend"))
    if accel:
        reasons.append(f"Wachstum beschleunigt sich ({pct(growth)} zuletzt vs. {pct(hist_g)} im Schnitt)")
    elif n and up < n - 1:
        risks.append("Umsatz ist in mehreren Jahren nicht gewachsen")

    # 3. Klein anfangen
    mc = s.get("market_cap")
    p = tiers(mc, [(2e9, 15), (10e9, 12), (30e9, 8), (100e9, 4)], higher_is_better=False) or (1 if mc else 0)
    c.append(crit("Größe / Luft nach oben", big(mc), p, 15, "100-Bagger starten klein – ab 100 Mrd. wird 100x unrealistisch"))
    if mc and mc < 10e9:
        reasons.append(f"Noch klein (Börsenwert {big(mc)}) – viel Raum für Vervielfachung")
    elif mc and mc > 300e9:
        risks.append(f"Schon sehr groß ({big(mc)}) – eine Vervielfachung ist schwer")

    # 4. Skalierbarkeit
    gm = s.get("gross_margin")
    p = tiers(gm, [(0.70, 10), (0.50, 7), (0.35, 4), (0.20, 1)])
    c.append(crit("Skalierbarkeit (Bruttomarge)", pct(gm), p, 10, "Jeder zusätzliche Umsatz bringt viel Gewinn"))
    if gm and gm >= 0.60:
        reasons.append(f"Skalierbares Geschäftsmodell (Bruttomarge {pct(gm)})")
    elif gm is not None and gm < 0.20:
        risks.append(f"Niedrige Bruttomarge ({pct(gm)}) – Wachstum ist teuer erkauft")

    # 5. Gründer / Insider
    ins = s.get("insider_pct")
    p = tiers(ins, [(0.15, 10), (0.05, 6), (0.01, 2)])
    c.append(crit("Gründer/Insider-Anteil", pct(ins, 1), p, 10, "Mayer: Eigentümer-Manager mit eigenem Geld im Spiel"))
    if ins and ins >= 0.10:
        reasons.append(f"Insider halten {pct(ins)} – Management zieht mit den Aktionären an einem Strang")

    # 6. Innovationskraft
    rnd, rev_l = s.get("rnd_latest"), s.get("revenue_latest")
    ri = rnd / rev_l if rnd and rev_l else None
    p = tiers(ri, [(0.15, 6), (0.08, 4), (0.03, 2)]) + (4 if theme else 0)
    c.append(crit("Innovationskraft", (f"F&E {pct(ri)}" if ri is not None else "F&E –") + (f" · {theme}" if theme else ""),
                  p, 10, "Forschungsquote und Zukunftsthema"))
    if theme:
        reasons.append(f"Zukunftsthema: {theme}")

    # 7. Weg zur Profitabilität (operativer Hebel)
    nm = {y: ni_hist[y] / rev_hist[y] for y in _years(ni_hist, rev_hist) if rev_hist[y] > 0}
    nm_first, nm_last = (nm[min(nm)], nm[max(nm)]) if len(nm) >= 2 else (None, s.get("profit_margin"))
    if nm_last is not None and nm_last >= 0.10:
        p, shown = 10, f"profitabel ({pct(nm_last)} Nettomarge)"
    elif nm_first is not None and nm_last - nm_first >= 0.10:
        p, shown = 8, f"Marge {pct(nm_first)} → {pct(nm_last)}"
    elif nm_first is not None and nm_last - nm_first >= 0.03:
        p, shown = 5, f"Marge {pct(nm_first)} → {pct(nm_last)}"
    elif nm_last is not None and nm_last > 0:
        p, shown = 4, f"knapp profitabel ({pct(nm_last)})"
    else:
        p, shown = 0, (f"Marge {pct(nm_first)} → {pct(nm_last)}" if nm_first is not None else pct(nm_last))
    c.append(crit("Weg zur Profitabilität", shown, p, 10, "Mit dem Wachstum sollten die Verluste schrumpfen"))
    if p == 8:
        reasons.append(f"Verluste schrumpfen schnell (Nettomarge {pct(nm_first)} → {pct(nm_last)})")
    elif p == 0 and nm_last is not None and nm_last < 0:
        risks.append(f"Noch nicht profitabel und keine klare Verbesserung (Nettomarge {pct(nm_last)})")

    # 8. Startpreis im Verhältnis zum Wachstum ("Zwillingsmotor": Wachstum + steigende Bewertung)
    ps = s.get("ps")
    gps = ps / (growth * 100) if ps and growth and growth > 0 else None
    p = tiers(gps, [(0.15, 10), (0.30, 7), (0.60, 4), (1.0, 1)], higher_is_better=False) if gps is not None else 0
    c.append(crit("Preis vs. Wachstum", f"KUV {num(ps)} bei {pct(growth)} Wachstum" if ps else "–", p, 10,
                  "Nicht zu teuer einsteigen: KUV ÷ Wachstum in % klein"))
    if gps is not None and gps <= 0.15:
        reasons.append(f"Günstig im Verhältnis zum Wachstum (KUV {num(ps)})")
    if ps and ps > 30:
        risks.append(f"Sehr hoch bewertet: {num(ps, 0)}-facher Umsatz – viel Erfolg schon eingepreist")

    # 9. Finanzielle Reichweite
    cash, debt = s.get("total_cash") or 0, s.get("total_debt") or 0
    ni_ttm = s.get("net_income_ttm")
    if ni_ttm is not None and ni_ttm < 0:
        years = (cash - debt) / -ni_ttm if -ni_ttm > 0 else None
        p = 5 if years and years >= 3 else 3 if years and years >= 1.5 else 0
        shown = f"Geld reicht ~{years:.1f} Jahre" if years and years > 0 else "mehr Schulden als Cash"
        if p == 0:
            risks.append("Geld reicht nicht lange – Kapitalerhöhung (Verwässerung) wahrscheinlich")
    else:
        p = 5 if cash >= debt else 3
        shown = f"profitabel · Cash {big(cash)} / Schulden {big(debt)}"
    c.append(crit("Finanzielle Reichweite", shown, p, 5, "Genug Geld, um bis zur Profitabilität durchzuhalten"))

    hi = s.get("fifty_two_high")
    if hi and price < hi * 0.5:
        risks.append("Mehr als 50 % unter dem 52-Wochen-Hoch – hohe Schwankungen")
    beta = s.get("beta")
    if beta and beta > 2:
        risks.append(f"Sehr volatil (Beta {num(beta)})")
    risks.append("Spekulativ: Totalverlust möglich – nur kleine Positionen")

    score = sum(x["points"] for x in c)
    growth_pts = sum(x["points"] for x in c if x["name"] in (
        "Wachstumstempo", "Wachstums-Beständigkeit", "Weg zur Profitabilität", "Finanzielle Reichweite", "Innovationskraft"))
    chance = "Hoch" if growth_pts >= 44 else "Mittel" if growth_pts >= 30 else "Niedrig"
    label = ("Hohes Bagger-Potenzial" if score >= 70 else "Spannend" if score >= 55
             else "Beobachten" if score >= 40 else "Noch zu früh/zu teuer")
    d = DECAY_BY_CHANCE[chance]
    modelable = (_revenue(s) or 0) >= MIN_REVENUE_FOR_MODEL
    bagger = {"low": bagger_multiple(s, 0.5, 0.5, 12, 0.02, d - 0.10, cap=0.20),
              "base": bagger_multiple(s, 1.0, 1.0, 22, 0.05, d, cap=0.80),
              "high": bagger_multiple(s, 1.4, 1.3, 35, 0.08, d + 0.03, cap=1.0)} if modelable else None
    tp = s.get("target_price")
    extra = {
        **_valuation_fields(s, *valuation_innovation(s, chance)),
        "theme": theme, "upside": tp / price - 1 if tp else None,
        "growth_chance": chance, "growth_points": f"{growth_pts}/55", "bagger": bagger,
        "metrics": {"Umsatzwachstum": pct(growth), "Bruttomarge": pct(gm), "KUV": num(ps),
                    "Marktkap.": big(mc), "Insider": pct(ins, 1), "Kursziel Analysten": num(tp, 2)},
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

    sector, industry = s.get("sector") or "", (s.get("industry") or "").lower()
    cyclical = sector in ("Energy", "Basic Materials") or "semiconductor equipment" in industry or "auto" in industry
    if sector in ("Energy", "Basic Materials"):
        growth = min(growth, 0.10) if growth is not None else None  # Rohstoff-Umsatz schwankt mit Preisen/Übernahmen
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
    if cyclical:
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
