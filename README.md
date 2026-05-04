# Cars24 People & Culture Central — Live Dashboard

Real-time replacement for the monthly People & Culture deck. Same visual style, same KPIs, refreshes daily at 6 AM IST.

## How to view

### Local (right now)
Already visible in the Launch preview panel. Or open:
```
file:///Users/a28819/Desktop/Claude%20filer/pc-central-dashboard/index.html
```

Drag-drop `index.html` into Chrome / Safari to view at any time.

### Local with live reload
```bash
cd "/Users/a28819/Desktop/Claude filer/pc-central-dashboard"
python3 -m http.server 8000
# Then open http://localhost:8000
```

### Deploy to Netlify (zero config)
1. Drag the `pc-central-dashboard` folder onto https://app.netlify.com/drop
2. Netlify gives you a URL like `https://cars24-pc-central.netlify.app`
3. Done. Daily JSON refreshes update the dashboard without redeploys (the agent rewrites `dashboard-data.json` and Netlify serves the latest).

## How the data refresh works

```
                  ┌──────────────────────────────────────────────┐
                  │  Cron: daily 6:00 AM IST                     │
                  │  → dashboard-refresh agent fires             │
                  └──────────────────┬───────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
  Recruitment            Joining Master              Tech & Product
  Metrics sheet          (gold mine)                 sheet
  (pre-aggregated)       (raw rows)                  (POD × cost)
        │                            │                            │
        └────────────────┬───────────┴────────────────────────────┘
                         │
                         ▼
           dashboard-data.json (rewritten daily)
                         │
                         ▼
                index.html reads JSON + renders
```

## Files

| File | Purpose |
|---|---|
| `index.html` | Single-page dashboard (Tailwind + Chart.js via CDN). All 11 sections matching the deck. |
| `dashboard-data.json` | Live data — rewritten daily by the agent. Contains every metric the dashboard shows. |
| `refresh_data.py` | Manual-run fallback if the agent is unavailable. Documents the JSON shape contract. |
| `README.md` | This file. |

## Sections (matching the April 2026 deck)

1. **Overview** — 8 headline KPI cards + joinings/attrition trend lines (last 6 months)
2. **Recruitment KPIs** — same 8 KPIs + by-function breakdown table
3. **Leadership Hiring** — B4+ counts, mix, list of names
4. **Sourcing Mix** — overall pie + by-function inbound/outbound bars
5. **Diversity** — female/male share, by-function bars, by-band bars
6. **Tech & Product** — Tech HC, Product HC, monthly cost, open roles + Backend/Frontend/Mobile SDE-1/2/3 doughnuts
7. **Glassdoor** — Rating, Recommend, CEO Approval, Business Outlook
8. **Attrition** — Overall, high-attrition zones, low-attrition zones, top exit drivers
9. **Offer Drops** — Total, rate, top function, by-function bars
10. **TA Pipeline** — Active reqs, closures, YTJ, recruiter productivity
11. **Automation** — All 25 agents with status / last run / next run

## Data sources (verified)

| Sheet | File ID |
|---|---|
| Recruitment Metrics | `1x6eJzZtn2xYYFomk4Is3hcDucmq98uOr4IzQiBbIePM` |
| Joining Master | `1xb6TtAdaCUUHTjxKza2wvgktf26m_BZIa7glQzaOPgY` |
| Tech & Product | `1TzXVJ_V_g9PiSfT0NtfbV2oHsoVsRTPuTJtmmalE8uc` |
| Third Party #1 | `1ueWrvNXpwTimz91ZhCu7rFKsucR-gS7A1oTDaI4QSGo` |
| ATS Superset (manual) | `Desktop/Claude filer/ats-superset/latest.csv` |

## Operating notes

- Dashboard works offline once loaded — JSON is fetched once on page load
- Refresh badge in header shows last data write timestamp + pulses green
- Charts use Chart.js (no API key, no vendor cost)
- Tailwind CSS via CDN (no build step)
- All copy is "Cars24" (never CARS24)
- Zero bot signatures anywhere

## Manually refresh data

If you need to force-refresh outside the daily schedule:
```bash
# Trigger the agent now via the Scheduled Tasks panel,
# OR rewrite the JSON manually and reload the page.
```

The agent is at `~/.claude/agents/dashboard-refresh.md`.
The schedule is in the Claude Code "Scheduled" sidebar — search for `dashboard-refresh`.
