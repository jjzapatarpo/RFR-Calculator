from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# ── Holiday helpers ────────────────────────────────────────────────────────────

def get_uk_holidays():
    try:
        r = requests.get("https://www.gov.uk/bank-holidays.json", timeout=10)
        data = r.json()
        return [e["date"] for e in data["england-and-wales"]["events"]]
    except Exception:
        return []

def get_us_holidays():
    """NYSE holidays: fixed + floating (MLK, Presidents, Memorial, Labor, Thanksgiving)."""
    hols = []
    for y in range(2020, 2032):
        # Fixed
        for mo, da in [(1,1),(7,4),(12,25)]:
            hols.append(f"{y}-{mo:02d}-{da:02d}")
        # MLK - 3rd Monday January
        hols.append(_nth_weekday(y, 1, 0, 3))
        # Presidents - 3rd Monday February
        hols.append(_nth_weekday(y, 2, 0, 3))
        # Memorial - last Monday May
        hols.append(_last_weekday(y, 5, 0))
        # Labor - 1st Monday September
        hols.append(_nth_weekday(y, 9, 0, 1))
        # Thanksgiving - 4th Thursday November
        hols.append(_nth_weekday(y, 11, 3, 4))
    return hols

def _nth_weekday(year, month, weekday, n):
    d = datetime(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d.strftime("%Y-%m-%d")
        d += timedelta(days=1)

def _last_weekday(year, month, weekday):
    if month == 12:
        last = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = datetime(year, month + 1, 1) - timedelta(days=1)
    while last.weekday() != weekday:
        last -= timedelta(days=1)
    return last.strftime("%Y-%m-%d")

def is_bizday(date_str, holidays):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.weekday() < 5 and date_str not in holidays

def add_bizdays(date_str, n, holidays):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            added += 1
    return d.strftime("%Y-%m-%d")

def days_between(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days

# ── FRED fetch ─────────────────────────────────────────────────────────────────

def fetch_fred(series_id, api_key):
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=asc"
    )
    r = requests.get(url, timeout=15)
    data = r.json()
    if "error_message" in data:
        raise ValueError(data["error_message"])
    obs = [o for o in data["observations"] if o["value"] not in (".", "NA")]
    return [{"date": o["date"], "rate": float(o["value"])} for o in obs]

# ── Core compounding engine ────────────────────────────────────────────────────

def compute(rates_raw, start, end, base, margin, cas, principal, subperiods, decimals):
    today = datetime.today().strftime("%Y-%m-%d")
    last_available = rates_raw[-1]["date"]

    # Forward-fill if needed
    filled_dates = []
    rates = list(rates_raw)
    limit = max(end, today)
    cursor = last_available
    while cursor < limit:
        cursor = add_bizdays(cursor, 1, [])  # rough forward; holidays applied below
        if cursor <= limit:
            rates.append({"date": cursor, "rate": rates[-1]["rate"], "estimated": True})
            filled_dates.append(cursor)

    rate_map = {r["date"]: r for r in rates}
    all_dates = [r["date"] for r in rates]

    # Determine holiday calendar
    # (passed in as argument to this function via the route)
    # We rebuild bizday list from all_dates filtering by holidays stored in rate_map context
    # Holidays are passed separately - see route below
    return {
        "rates": rates,
        "filled_dates": filled_dates,
        "last_available": last_available,
        "rate_map": rate_map,
        "all_dates": all_dates,
    }

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/calculate", methods=["POST"])
def calculate():
    try:
        body = request.json
        api_key   = body.get("api_key", "").strip()
        rate_type = body.get("rate_type", "SONIA")
        start     = body.get("start")
        end       = body.get("end")
        base      = int(body.get("base", 365))
        margin    = float(body.get("margin", 0))
        cas       = float(body.get("cas", 0))
        principal = float(body.get("principal", 0))
        subperiods = body.get("subperiods", [])
        decimals  = 6 if rate_type == "SONIA" else 7

        if not api_key:
            return jsonify({"error": "No FRED API key provided."}), 400

        series_id = "IUDSOIA" if rate_type == "SONIA" else "SOFR"
        raw = fetch_fred(series_id, api_key)

    # Load holidays server-side
    holidays = get_uk_holidays() if rate_type == "SONIA" else get_us_holidays()
    holiday_set = set(holidays)

    today = datetime.today().strftime("%Y-%m-%d")
    last_available = raw[-1]["date"]

    # Forward-fill tail
    rates = list(raw)
    filled_dates = []
    limit = max(end, today)
    cursor = last_available
    while cursor < limit:
        cursor = add_bizdays(cursor, 1, list(holiday_set))
        if cursor <= limit:
            rates.append({"date": cursor, "rate": rates[-1]["rate"], "estimated": True})
            filled_dates.append(cursor)

    rate_map = {r["date"]: r for r in rates}
    all_biz = [r["date"] for r in rates if is_bizday(r["date"], holiday_set)]

    # Build 5-day lookback maps
    start_map = {}
    end_map = {}
    for i in range(len(all_biz) - 5):
        start_map[all_biz[i]] = all_biz[i + 5]
        end_map[all_biz[i]]   = all_biz[i + 5]

    inv_start = {v: k for k, v in start_map.items()}
    inv_end   = {v: k for k, v in end_map.items()}

    if start not in inv_start:
        return jsonify({"error": f"Start date {start} could not be mapped. Check it is a business day within the available data range."}), 400
    if end not in inv_end:
        return jsonify({"error": f"End date {end} could not be mapped. Check it is a business day and rates are available."}), 400

    period_start_raw = inv_start[start]
    period_end_raw   = inv_end[end]

    s_idx = all_biz.index(period_start_raw)
    e_idx = all_biz.index(period_end_raw)
    period_dates = all_biz[s_idx:e_idx + 1]

    # Build rows
    rows = []
    cum_days = 0
    comp_factor = 1.0

    for i, d in enumerate(period_dates):
        r_info = rate_map.get(d) or rate_map.get(period_dates[i-1]) or rates[-1]
        rate = r_info["rate"]
        estimated = bool(r_info.get("estimated", False))
        start_d = start_map.get(d, d)
        end_d   = end_map.get(d, add_bizdays(d, 1, list(holiday_set)))
        diff_days = days_between(start_d, end_d)

        unann = (rate / 100) * diff_days / base
        comp_factor *= (1 + unann)
        cum_days += diff_days
        ann_cum = round((comp_factor - 1) * base / cum_days, decimals)
        unann_cum = ann_cum * cum_days / base

        rows.append({
            "date": d,
            "rate": rate,
            "start_date": start_d,
            "end_date": end_d,
            "diff_days": diff_days,
            "cum_days": cum_days,
            "comp_factor": comp_factor,
            "ann_cum_comp": ann_cum,
            "unann_cum": unann_cum,
            "estimated": estimated,
            "margin": margin,
            "cas": cas,
            "principal": principal,
        })

    # Non-cumulative compounded
    for i, row in enumerate(rows):
        prev_unann = rows[i-1]["unann_cum"] if i > 0 else 0
        aux_diff = row["unann_cum"] - prev_unann
        row["non_cum_comp"] = aux_diff * base / row["diff_days"]

    # Apply subperiods
    subperiods_sorted = sorted(subperiods, key=lambda x: x["date"])
    for sp in subperiods_sorted:
        for row in rows:
            if row["start_date"] >= sp["date"]:
                row["margin"]    = sp["margin"]
                row["principal"] = sp["principal"]
                row["cas"]       = sp["cas"]

    # Interest
    for row in rows:
        row["rfr_interest"]    = row["non_cum_comp"] * row["principal"] * row["diff_days"] / base
        row["cas_interest"]    = row["cas"] * row["principal"] * row["diff_days"] / base
        row["margin_interest"] = row["margin"] * row["principal"] * row["diff_days"] / base
        row["total_interest"]  = row["rfr_interest"] + row["cas_interest"] + row["margin_interest"]

    main_rate     = rows[-1]["ann_cum_comp"]
    total_interest = sum(r["total_interest"] for r in rows)
    total_days    = sum(r["diff_days"] for r in rows)
    has_estimate  = any(r["estimated"] for r in rows)
    first_est_date = next((r["date"] for r in rows if r["estimated"]), None)

    # Final rate available date (approx 3 biz days after last available)
    final_rate_date = None
    if filled_dates:
        final_rate_date = add_bizdays(last_available, len(filled_dates) + 3, list(holiday_set))

    # Subperiod rates
    sub_rates = {}
    if subperiods_sorted:
        key_dates = [sp["date"] for sp in subperiods_sorted] + [end]
        for x in range(len(key_dates) - 1):
            seg_start = key_dates[x]
            seg_end   = key_dates[x + 1]
            seg = [r for r in rows if r["start_date"] >= seg_start and r["end_date"] <= seg_end]
            if not seg:
                continue
            n = sum(r["diff_days"] for r in seg)
            interest = sum(r["total_interest"] for r in seg)
            sp = subperiods_sorted[x] if x < len(subperiods_sorted) else subperiods_sorted[-1]
            rate_aux = round((interest / sp["principal"]) * (base / n) - sp["margin"] - sp["cas"], decimals)
            sub_rates[seg_end] = rate_aux
        sub_rates["Rate for notice"] = main_rate

    return jsonify({
        "main_rate": main_rate,
        "total_interest": total_interest,
        "total_days": total_days,
        "has_estimate": has_estimate,
        "first_est_date": first_est_date,
        "final_rate_date": final_rate_date,
        "last_available": last_available,
        "filled_dates": filled_dates,
        "sub_rates": sub_rates,
        "decimals": decimals,
        "rows": rows,
    })

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500

@app.route("/api/test-key", methods=["POST"])
def test_key():
    api_key = request.json.get("api_key", "").strip()
    try:
        r = requests.get(
            f"https://api.stlouisfed.org/fred/series?series_id=SOFR&api_key={api_key}&file_type=json",
            timeout=10
        )
        data = r.json()
        if "error_message" in data:
            return jsonify({"ok": False, "message": data["error_message"]}), 400
        return jsonify({"ok": True, "message": "Connected to FRED successfully."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
