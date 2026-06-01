# RFR Calculator — Altrium Financial Services

Compounded-in-arrears calculator for SONIA and SOFR. Fetches live rate data from FRED (St. Louis Fed), applies a 5-day lookback convention, and produces a full daily calculation breakdown with Excel export.

---

## Setup

Python 3.8 or later required.

```bash
pip install -r requirements.txt
python app.py
```

Open your browser at `http://localhost:5000`.

A free FRED API key is required to fetch rate data. Get one at https://fred.stlouisfed.org/docs/api/api_key.html and enter it in the sidebar. It is saved in your browser's local storage.

---

## Rate conventions

| Rate  | Series  | Holidays    | Decimals | Default base |
|-------|---------|-------------|----------|--------------|
| SONIA | IUDSOIA | UK (gov.uk) | 6        | ACT/365      |
| SOFR  | SOFR    | NYSE        | 7        | ACT/360      |

When the interest period end date falls beyond the last published rate on FRED, the app forward-fills the tail using the last known rate. Affected rows are flagged in the UI and highlighted in the Excel export.
