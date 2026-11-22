"""Aktien-Universum, aus dem täglich ausgewählt wird.

Einfach Ticker ergänzen oder entfernen (Yahoo-Finance-Symbole).
Nicht mehr existierende Ticker werden beim Scan automatisch übersprungen.
"""

# Innovations-/Wachstumsaktien mit Thema (Kandidaten für 10- bis 100-Bagger)
INNOVATION = {
    # Künstliche Intelligenz & Daten
    "PLTR": "Künstliche Intelligenz", "TEM": "KI in der Medizin", "SOUN": "Sprach-KI",
    "AI": "Unternehmens-KI", "SNOW": "Daten-Cloud", "MDB": "Datenbanken",
    "DDOG": "Cloud-Monitoring", "APP": "KI-Werbung", "RDDT": "Social Media & KI-Daten",
    "DUOL": "KI-Bildung", "IOT": "Industrie-IoT", "PATH": "Automatisierung",
    "NBIS": "KI-Infrastruktur", "CRWV": "KI-Cloud",
    # Halbleiter
    "ARM": "Chip-Design", "CRDO": "KI-Konnektivität", "ALAB": "KI-Konnektivität",
    "AMBA": "Edge-KI-Chips", "LSCC": "Low-Power-Chips",
    # Cybersecurity
    "CRWD": "Cybersecurity", "ZS": "Cybersecurity", "NET": "Edge-Netzwerk", "S": "Cybersecurity",
    # Raumfahrt & Luftfahrt
    "RKLB": "Raumfahrt", "ASTS": "Satelliten-Mobilfunk", "LUNR": "Mond-Missionen",
    "PL": "Erdbeobachtung", "RDW": "Weltraum-Infrastruktur",
    "JOBY": "Flugtaxis", "ACHR": "Flugtaxis",
    # Quantencomputing
    "IONQ": "Quantencomputing", "RGTI": "Quantencomputing", "QBTS": "Quantencomputing",
    # Biotech & Gesundheit
    "CRSP": "Gen-Editing", "NTLA": "Gen-Editing", "BEAM": "Base-Editing",
    "RXRX": "KI-Medikamentenforschung", "TWST": "Synthetische Biologie",
    "HIMS": "Digitale Gesundheit", "ISRG": "Chirurgie-Robotik",
    # Fintech
    "SOFI": "Digitalbank", "NU": "Digitalbank Lateinamerika", "HOOD": "Trading & Krypto",
    "AFRM": "Buy now, pay later", "TOST": "Restaurant-Software",
    # Plattformen & E-Commerce
    "MELI": "E-Commerce Lateinamerika", "SE": "E-Commerce Südostasien",
    "SHOP": "E-Commerce-Plattform", "CPNG": "E-Commerce Korea",
    # Energie der Zukunft
    "OKLO": "Mini-Atomreaktoren", "SMR": "Mini-Atomreaktoren", "NNE": "Mikroreaktoren",
    "FLNC": "Energiespeicher", "EOSE": "Energiespeicher",
    # Robotik & Autonomie
    "TSLA": "Robotik & Autonomes Fahren", "SYM": "Lager-Robotik", "SERV": "Liefer-Roboter",
}

# Qualitätsunternehmen, wie Warren Buffett sie analysieren würde
VALUE = [
    # Berkshire-Klassiker
    "AAPL", "KO", "AXP", "BAC", "MCO", "CVX", "OXY", "CB", "KR", "VRSN", "DVA", "BRK-B",
    # Zahlungsverkehr & Finanzinfrastruktur
    "V", "MA", "SPGI", "MSCI", "ICE", "CME", "TRV", "AON", "MMC",
    # Tech mit Burggraben
    "MSFT", "GOOGL", "META", "TXN", "QCOM", "KLAC", "LRCX", "CSCO", "ACN", "ADP", "TSM", "ASML", "SAP",
    # Konsum & Marken
    "PG", "PEP", "COST", "HD", "LOW", "MCD", "YUM", "SBUX", "NKE", "CL", "KMB", "HSY",
    "MO", "PM", "TJX", "ROST", "ORLY", "AZO", "DPZ", "POOL", "DEO", "UL",
    # Gesundheit
    "JNJ", "MRK", "ABBV", "UNH", "ZTS", "NVO", "DHR",
    # Industrie & Dienstleistungen
    "UNP", "CSX", "WM", "RSG", "CTAS", "ROL", "ITW", "GWW", "FAST", "VRSK", "NVR", "RELX",
]
