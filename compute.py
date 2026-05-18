"""
Cars24 P&C Central Dashboard — durable compute script.
Reads Base-Live + Rocket Offers CSVs, applies the SAME formula/logic as the
7-May commit 211847b (canonical), and patches dashboard-data.json in place.

Lives in the dashboard dir (NOT /tmp) so it survives macOS tmp cleanup.

Run: python3 compute.py
"""
from __future__ import annotations
import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()
WS = date(2026, 4, 26)

BASE_CSV = "/Users/a28819/Downloads/Base-Live Employee Data - Aug 2018  - Base sheet.csv"
RO_CSV   = "/Users/a28819/Downloads/Recruitment Metric_New - Rocket Offers.csv"
JSON_PATH = "/Users/a28819/Desktop/Claude filer/pc-central-dashboard/dashboard-data.json"


def parse_dt(s):
    s = (s or '').strip()
    if not s or s == '-':
        return None
    for fmt in ('%d-%b-%y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def fb(func, bu=''):
    f = (func or '').strip().lower()
    b = (bu or '').strip().lower()
    if 'product' in f:
        return 'Product'
    if 'tech' in f or 'engineering' in f or 'devops' in f:
        return 'Technology'
    if 'data' in f or 'risk' in f or 'business intelligence' in f:
        return 'BI DS'
    if 'business' in f and 'support' in b:
        return 'Business Support'
    if any(k in f for k in ['business', 'sales', 'operations', 'retail', 'collections', 'partner experience']):
        return 'Business (B1+B2)'
    return 'Other Support'


def main():
    base_joiners = []
    exits_dol = []
    active_total = 0
    func_active_b = Counter()
    func_exits_b = Counter()

    with open(BASE_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            status = (r.get('Employee Status') or '').strip()
            doj = parse_dt(r.get('DOJ', ''))
            dol = parse_dt(r.get('Date of Leaving', ''))
            if doj and WS <= doj <= TODAY:
                base_joiners.append(r)
            if dol and WS <= dol <= TODAY:
                exits_dol.append(r)
                func_exits_b[fb(r.get('Function'), r.get('Business Unit'))] += 1
            if status in ('Active', 'On Notice'):
                active_total += 1
                func_active_b[fb(r.get('Function'), r.get('Business Unit'))] += 1

    seniors = [r for r in base_joiners if (r.get('Band') or '').strip().upper().startswith(('B4', 'B5', 'B6', 'B7'))]

    attrition_by_func = {}
    for fn in ['Business (B1+B2)', 'Business Support', 'Product', 'Technology', 'BI DS', 'Other Support']:
        e = func_exits_b.get(fn, 0)
        a = func_active_b.get(fn, 0)
        attrition_by_func[fn] = round(e / a * 100, 4) if a else 0

    band_gender = {}
    for r in base_joiners:
        band_raw = (r.get('Band') or '').strip().upper().split()[0] if (r.get('Band') or '').strip() else 'Unknown'
        band = band_raw.replace(' TECH', '').replace(' T', '')
        if band not in band_gender:
            band_gender[band] = Counter()
        band_gender[band][(r.get('Gender') or '').strip()] += 1

    female_by_band = {}
    for b in ['B0', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7']:
        if b in band_gender:
            c = band_gender[b]
            total = c.get('Male', 0) + c.get('Female', 0)
            female_by_band[b] = round(c.get('Female', 0) / total * 100, 2) if total else 0

    day_counter = Counter((r.get('DOJ') or '').strip() for r in base_joiners)
    entity_counter = Counter((r.get('Entity') or '').strip() or 'Unknown' for r in base_joiners)

    ro_recs = Counter()
    with open(RO_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            doj = parse_dt(r.get('DOJ', ''))
            if doj and WS <= doj <= TODAY and (r.get('Joining Status') or '').strip() == 'Joined':
                ro_recs[(r.get('Recruiter') or '').strip()] += 1

    d = json.load(open(JSON_PATH))
    d['overview']['joinings'] = len(base_joiners)
    d['overview']['senior_b4_plus'] = len(seniors)
    d['overview']['active_hc'] = active_total
    d['overview']['exits_in_window'] = len(exits_dol)

    opening_hc = active_total + len(exits_dol)
    avg_hc = (opening_hc + active_total) / 2
    window_attrition = round(len(exits_dol) / avg_hc * 100, 4) if avg_hc else 0
    window_days = (TODAY - WS).days + 1
    d['overview']['overall_attrition_window'] = window_attrition
    d['overview']['overall_attrition_monthly_projected'] = (
        round(len(exits_dol) / avg_hc * (30 / window_days) * 100, 2) if avg_hc and window_days else 0
    )
    d['functionTable']['attrition_by'] = attrition_by_func

    d['overview']['active_recruiters'] = 17
    d['overview']['productivity'] = round(len(base_joiners) / 17, 1)

    d['leadership']['total'] = len(seniors)
    d['leadership']['list'] = [{
        'name': s.get('Emp Name', '').strip(),
        'band': s.get('Band', '').strip(),
        'designation': s.get('External Designation', '').strip(),
        'function': s.get('Function', '').strip(),
        'entity': s.get('Entity', '').strip(),
        'doj': s.get('DOJ', '').strip(),
        'gender': s.get('Gender', '').strip(),
    } for s in seniors]
    d['diversity']['by_band'] = female_by_band

    period_label = f"26 Apr → {TODAY.strftime('%-d %b').replace(' 0', ' ')} {TODAY.year}"
    d['period_label'] = period_label
    d['window'] = {
        'start': WS.strftime('%Y-%m-%d'),
        'end': TODAY.strftime('%Y-%m-%d'),
        'days': window_days,
    }

    d['trends'] = {
        "months": ["Jan-26", "Feb-26", "Mar-26", "Apr-26", f"26 Apr→{TODAY.strftime('%-d %b')}"],
        "joinings": [351, 340, 269, 232, d['overview']['joinings']],
        "attrition": [8.07, 11.75, 11.75, 18.96, d['overview']['attrition_30d']],
    }

    d['window_extras'] = {
        "by_day": {k: day_counter[k] for k in sorted(day_counter, key=lambda x: parse_dt(x) or date(1900, 1, 1))},
        "by_entity": dict(entity_counter),
        "top_recruiters": [{"name": k.replace('@cars24.com', ''), "joinings": v} for k, v in ro_recs.most_common(10)],
    }

    d['refreshed_at'] = datetime.now(IST).strftime('%d %b %Y · %H:%M IST')

    with open(JSON_PATH, 'w') as f:
        json.dump(d, f, indent=2)

    print(f"✅ Window: {WS.strftime('%d %b %Y')} — {TODAY.strftime('%d %b %Y')} ({window_days} days)")
    print(f"   Joinings: {len(base_joiners)} | Exits: {len(exits_dol)} | Window attrition: {window_attrition:.2f}%")
    print(f"   Active HC: {active_total} | Senior B4+: {len(seniors)} | Productivity: {d['overview']['productivity']}")
    print(f"   Trends OK | by_day={len(day_counter)} days | by_entity={len(entity_counter)} entities")
    print(f"   refreshed_at: {d['refreshed_at']}")


if __name__ == "__main__":
    main()
