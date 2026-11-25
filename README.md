# 📈 Aktien des Tages

Eine Web-App, die dir **jeden Tag neue Aktien-Vorschläge** in zwei Kategorien macht:

| Kategorie | Idee | Kriterien (je 0–100 Punkte) |
|---|---|---|
| 🚀 **Innovation · 10–100-Bagger** | Kleine, schnell wachsende Firmen mit disruptiven Technologien (KI, Raumfahrt, Quanten, Gen-Editing, Fintech, Mini-Atomreaktoren …) | Umsatzwachstum, Bruttomarge, Größe (Luft nach oben), Insider-Anteil, Cash vs. Schulden, F&E-Quote, Analysten-Kursziel, Trend |
| 🏛️ **Buffett-Value** | Qualitätsfirmen mit Burggraben zu einem vernünftigen Preis | Eigenkapitalrendite Ø ≥ 15 %, Gesamtkapitalrendite Ø ≥ 10 %, Bruttomarge ≥ 40 %, Nettomarge ≥ 15 %, stetiges Umsatz- und Gewinnwachstum, Cashflow jedes Jahr positiv, KGV ≤ 25, wenig Schulden, **Sicherheitsmarge** zum inneren Wert (DCF auf **Owner Earnings** = Gewinn + Abschreibungen − Erhaltungsinvestitionen; Wachstum 70 % Historie / 30 % Analysten; Mindestrendite 8–10 % je nach Risiko, 10 % Mindestrendite) |

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

## 🔎 Suche – jede Aktie analysieren

Oben in der App Ticker oder Namen eingeben. Du bekommst beide Bewertungen (Buffett & Innovation), die
Einstufung (Value, Growth, Qualität, Qualitäts-Wachstum, Spekulativ …), Merkmale (Dividende, zyklisch, defensiv …),
fairen Wert, Potenzial und Risiko.

- Aktien aus der täglichen Liste erscheinen **sofort**.
- Andere Aktien: **„Jetzt bewerten“** öffnet ein vorausgefülltes GitHub-Issue („Bewerten: …“). Absenden genügt –
  der Workflow `lookup.yml` bewertet die Aktie, schließt das Issue mit dem Ergebnis und nach ca. 2–3 Minuten
  zeigt die App die Analyse. Gesuchte Aktien werden danach täglich mit aktualisiert.
- Aus Sicherheitsgründen reagiert der Workflow nur auf Issues des Repo-Besitzers.

## Morningstar-Vergleich

Die App loggt sich **nicht** bei Morningstar ein. Stattdessen trägst du die Werte, die dich interessieren,
selbst in `scanner/morningstar.csv` ein (geht auch am Handy: Datei auf GitHub öffnen → ✏️ → Commit):

```csv
symbol,fair_value,stars,moat,uncertainty,date,currency
AAPL,180,3,wide,medium,2026-11-25,USD
TSM,500,4,wide,medium,2026-11-25,EUR
```

- `currency` (optional): Währung des Morningstar-Werts, z. B. `EUR` – wird automatisch in die Kurswährung umgerechnet
- `moat`: wide / narrow / none · `uncertainty`: low / medium / high / very high / extreme
- Nach dem Speichern rechnet der Workflow automatisch neu. Auf der Karte erscheint dann der Morningstar-Wert
  mit Sternen, Burggraben und dem Vergleich zur eigenen Schätzung.

## Anpassen

- **Aktien-Universum:** `scanner/universe.py` – Ticker hinzufügen/entfernen (Yahoo-Symbole, z. B. `SAP`, `ASML`).
- **Bewertungsregeln & Gewichte:** `scanner/scoring.py`.
- **Anzahl Vorschläge:** `PICKS_PER_DAY` / `POOL_SIZE` in `scanner/scan.py`.
