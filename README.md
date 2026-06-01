# RFR Calculator — Altrium Financial Services

Compounded-in-arrears calculator for SONIA and SOFR. Fetches live rate data
from FRED (St. Louis Fed), applies 5-day lookback convention, and produces
a full daily calculation breakdown with Excel export.

---

## Quick start (local)

### 1. Requirements
Python 3.8 or later.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run
```bash
python app.py
```

Open your browser at: http://localhost:5000

### 4. FRED API key
Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html
Enter it in the sidebar. It is saved in your browser's local storage —
you only need to enter it once per machine.

---

## Sharing with colleagues (same office network)

Run the app on one machine:
```bash
python app.py
```

Find your local IP (run `ipconfig` on Windows or `ifconfig` on Mac/Linux).
Colleagues on the same network can then access the app at:
```
http://YOUR_LOCAL_IP:5000
```

Each colleague should enter their own FRED API key in the sidebar.

To allow connections from other machines, change the last line in app.py to:
```python
app.run(debug=False, host='0.0.0.0', port=5000)
```

---

## Cloud deployment (everyone, anywhere)

### Option A — Railway (easiest, ~5 minutes)
1. Push this folder to a GitHub repo
2. Go to https://railway.app and create a new project from that repo
3. Railway auto-detects Flask and deploys it
4. You get a public URL to share with anyone

### Option B — Render
1. Push to GitHub
2. Go to https://render.com → New Web Service
3. Set start command to: `python app.py`
4. Deploy. Free tier available.

### Option C — VPS (most control)
Any Linux VPS (Hetzner, DigitalOcean, etc.):
```bash
pip install -r requirements.txt gunicorn
gunicorn app:app -w 2 -b 0.0.0.0:5000
```
Use nginx as a reverse proxy and add a domain + SSL certificate (Let's Encrypt).

---

## Future: embedding in Altrium Connect

The Flask `/api/calculate` and `/api/test-key` endpoints are already
REST-compatible. When Altrium Connect is ready:
- The front-end (index.html) can be ported as a React/Vue component
- The Flask API moves behind the platform's existing infrastructure
- API keys can be managed per-user through the platform's auth system
  rather than browser local storage

---

## Files

```
rfr_calculator/
├── app.py              Flask backend — FRED proxy + compounding engine
├── requirements.txt    Python dependencies
├── templates/
│   └── index.html      Front-end (served by Flask)
└── README.md           This file
```

---

## Rate conventions

| Rate  | Series   | Holidays        | Decimals | Default base |
|-------|----------|-----------------|----------|--------------|
| SONIA | IUDSOIA  | UK (gov.uk)     | 6        | ACT/365      |
| SOFR  | SOFR     | NYSE            | 7        | ACT/360      |

Forward-fill: when the interest period end date falls beyond the last
published rate on FRED, the app forward-fills the tail using the last
known rate. Affected rows are flagged in the UI and highlighted in
#FFCCCC in the Excel export.
