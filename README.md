# 📈 Aktien des Tages

Eine Web-App, die dir **jeden Tag neue Aktien-Vorschläge** in zwei Kategorien macht:

| Kategorie | Idee | Kriterien (je 0–100 Punkte) |
|---|---|---|
| 🚀 **Innovation · 10–100-Bagger** | Kleine, schnell wachsende Firmen mit disruptiven Technologien (KI, Raumfahrt, Quanten, Gen-Editing, Fintech, Mini-Atomreaktoren …) | Umsatzwachstum, Bruttomarge, Größe (Luft nach oben), Insider-Anteil, Cash vs. Schulden, F&E-Quote, Analysten-Kursziel, Trend |
| 🏛️ **Buffett-Value** | Qualitätsfirmen mit Burggraben zu einem vernünftigen Preis | Eigenkapitalrendite, Verschuldung, operative Marge, Gewinn-Beständigkeit, Free-Cashflow-Marge, **Sicherheitsmarge** zum inneren Wert (DCF, 10 % Abzinsung) |

Pro Kategorie werden täglich **6 Aktien** gezogen – gewichtet aus den 15 besten. So wechselt die Auswahl täglich,
starke Aktien tauchen aber immer wieder auf. „Neu heute“ markiert Aktien, die gestern nicht dabei waren.
Jede Karte zeigt Gründe ✓, Risiken ! und die Punkte im Detail. Ältere Tage lassen sich über das Datum-Menü ansehen.

> ⚠️ Keine Anlageberatung. Automatische Auswertung öffentlicher Kennzahlen (Yahoo Finance) mit einem einfachen Punktesystem.

## So funktioniert's

```
GitHub Actions (täglich)  →  scanner/scan.py  →  docs/data/*.json  →  docs/index.html (GitHub Pages)
```

## Einrichten (einmalig)

1. Diesen Branch in `main` mergen (geplante Workflows laufen nur auf dem Standard-Branch).
2. **Settings → Pages** → Source: *Deploy from a branch* → `main` / `docs`.
3. **Actions → „Tägliche Aktien-Vorschläge“ → Run workflow** für die ersten Daten.
4. Danach läuft der Scan automatisch Di–Sa morgens. Seite öffnen und auf dem Handy „Zum Startbildschirm hinzufügen“.

## Lokal ausführen

```bash
pip install -r requirements.txt
python scanner/scan.py            # ~2–3 Minuten
python -m http.server -d docs 8000
# -> http://localhost:8000
```

## Anpassen

- **Aktien-Universum:** `scanner/universe.py` – Ticker hinzufügen/entfernen (Yahoo-Symbole, z. B. `SAP`, `ASML`).
- **Bewertungsregeln & Gewichte:** `scanner/scoring.py`.
- **Anzahl Vorschläge:** `PICKS_PER_DAY` / `POOL_SIZE` in `scanner/scan.py`.
