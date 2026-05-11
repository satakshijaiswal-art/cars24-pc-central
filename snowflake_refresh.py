"""Snowflake side-car for the P&C dashboard.

Pulls 4 metrics LIVE from CSPL_HR_DB and patches them into dashboard-data.json:
  - Time to Fill (d)        ← ATS OFFER_LETTERS_DETAILS ⋈ REQUISITIONS
  - Avg TAT — Open Roles    ← ATS REQUISITIONS (STATUS=Open)
  - Active Reqs (Open)      ← ATS REQUISITIONS (STATUS=Open)
  - Female %                ← ATS APPLICANTS ⋈ OFFER_LETTERS_DETAILS (window joiners)

Not yet wired into the cron loop because the local launchd user has no
Snowflake connector / creds. Run path (manual or via cron once creds land):

    SNOWFLAKE_USER=...  SNOWFLAKE_ACCOUNT=...  SNOWFLAKE_PASSWORD=... \
    python3 snowflake_refresh.py /Users/a28819/Desktop/Claude\ filer/pc-central-dashboard/dashboard-data.json

Until then, this same SQL is run via Claude's Snowflake MCP and the
results are patched into dashboard-data.json by hand at refresh time.
"""

from __future__ import annotations
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

WINDOW_START = "2026-04-26"
WINDOW_END   = "2026-05-04"

SQL = {
    "open_reqs": """
        SELECT COUNT(*)                                       AS active_reqs_open,
               AVG(DATEDIFF(day, START_DATE, CURRENT_DATE())) AS avg_tat_open_days
        FROM CSPL_HR_DB.HR_ATS_PUBLIC.REQUISITIONS
        WHERE STATUS='Open' AND COALESCE(_FIVETRAN_DELETED,FALSE)=FALSE
    """,
    "ttf": f"""
        SELECT AVG(DATEDIFF(day, r.START_DATE, old.JOINING_DATE)) AS avg_ttf_days,
               COUNT(*)                                            AS n
        FROM CSPL_HR_DB.HR_ATS_PUBLIC.OFFER_LETTERS_DETAILS old
        JOIN CSPL_HR_DB.HR_ATS_PUBLIC.REQUISITIONS         r
          ON r.REQUISITION_ID = old.REQUISITION_ID
        WHERE old.JOINING_DATE BETWEEN '{WINDOW_START}' AND '{WINDOW_END}'
          AND r.START_DATE IS NOT NULL
    """,
    "diversity": f"""
        SELECT SUM(CASE WHEN LOWER(a.GENDER)='female' THEN 1 ELSE 0 END) AS female_n,
               SUM(CASE WHEN LOWER(a.GENDER)='male'   THEN 1 ELSE 0 END) AS male_n
        FROM CSPL_HR_DB.HR_ATS_PUBLIC.APPLICANTS a
        JOIN CSPL_HR_DB.HR_ATS_PUBLIC.OFFER_LETTERS_DETAILS old
          ON old.APPLICANT_ID = a.ID
        WHERE old.JOINING_DATE BETWEEN '{WINDOW_START}' AND '{WINDOW_END}'
          AND LOWER(a.GENDER) IN ('male','female')
    """,
}

def run_query(cur, sql):
    cur.execute(sql)
    cols = [c[0].lower() for c in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row))

def main(json_path: str):
    import snowflake.connector
    conn = snowflake.connector.connect(
        user      = os.environ["SNOWFLAKE_USER"],
        password  = os.environ["SNOWFLAKE_PASSWORD"],
        account   = os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database  = "CSPL_HR_DB",
        schema    = "HR_ATS_PUBLIC",
    )
    cur = conn.cursor()
    open_reqs = run_query(cur, SQL["open_reqs"])
    ttf       = run_query(cur, SQL["ttf"])
    div       = run_query(cur, SQL["diversity"])
    cur.close(); conn.close()

    with open(json_path) as f: d = json.load(f)
    ov = d["overview"]
    ov["open_reqs"]        = int(open_reqs["active_reqs_open"])
    ov["open_reqs_source"] = "snowflake"
    ov["tat"]              = round(float(open_reqs["avg_tat_open_days"] or 0), 1)
    ov["tat_data_rows"]    = int(open_reqs["active_reqs_open"])
    ov["tat_source"]       = "snowflake"
    ov["ttf"]              = round(float(ttf["avg_ttf_days"] or 0), 1)
    ov["ttf_data_rows"]    = int(ttf["n"] or 0)
    ov["ttf_source"]       = "snowflake"

    fem = int(div["female_n"] or 0); male = int(div["male_n"] or 0)
    base = fem + male
    ov["female_n"]         = fem
    ov["female_base_n"]    = base
    ov["female_pct"]       = round(100*fem/base, 2) if base else None
    ov["female_source"]    = "snowflake"
    ov["female_note"]      = f"Snowflake CSPL_HR_DB · {fem} Female / {base} ATS-tagged joiners with declared gender"

    d["refreshed_at"] = datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime("%d %b %Y · %H:%M IST")
    with open(json_path,"w") as f: json.dump(d,f,indent=2)
    print("Patched:", json_path)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: snowflake_refresh.py <dashboard-data.json>"); sys.exit(2)
    main(sys.argv[1])
