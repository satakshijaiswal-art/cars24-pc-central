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
    "talent_density": """
        WITH ALL_EMP AS (
          SELECT EMPLOYEE_ID, BAND, DATE_OF_JOINING, DATE_OF_EXIT, IS_ACTIVE, EMPLOYEE_STATUS
          FROM CSPL_HR_DB.HRMS_PUBLIC.EMPLOYEES
          UNION ALL
          SELECT EMPLOYEE_ID, BAND, DATE_OF_JOINING, DATE_OF_EXIT, IS_ACTIVE, EMPLOYEE_STATUS
          FROM CAPL_HR_DB.HRMS_CAPL_PUBLIC.EMPLOYEES
        ),
        ACTIVE AS (
          SELECT *, DATEDIFF(month, DATE_OF_JOINING, CURRENT_DATE()) AS TENURE_M
          FROM ALL_EMP
          WHERE IS_ACTIVE=TRUE AND EMPLOYEE_STATUS NOT ILIKE '%Inactive%'
        ),
        EXITS_90D AS (
          SELECT *, DATEDIFF(day, DATE_OF_JOINING, DATE_OF_EXIT) AS TENURE_DAYS
          FROM ALL_EMP
          WHERE DATE_OF_EXIT BETWEEN DATEADD(day,-90,CURRENT_DATE()) AND CURRENT_DATE()
        )
        SELECT
          (SELECT COUNT(*) FROM ACTIVE)                                                                          AS active_hc,
          (SELECT SUM(CASE WHEN BAND IN ('B4','B5','B6','Builder') THEN 1 ELSE 0 END) FROM ACTIVE)               AS builders_b4plus,
          ROUND(100.0*(SELECT SUM(CASE WHEN BAND IN ('B4','B5','B6','Builder') THEN 1 ELSE 0 END) FROM ACTIVE)
                /(SELECT COUNT(*) FROM ACTIVE),2)                                                                AS builder_density_pct,
          ROUND(100.0*(SELECT SUM(CASE WHEN TENURE_M<12 THEN 1 ELSE 0 END) FROM ACTIVE)
                /(SELECT COUNT(*) FROM ACTIVE),1)                                                                AS tenure_lt_1y_pct,
          ROUND(100.0*(SELECT SUM(CASE WHEN TENURE_M>=36 THEN 1 ELSE 0 END) FROM ACTIVE)
                /(SELECT COUNT(*) FROM ACTIVE),1)                                                                AS tenure_3y_plus_pct,
          (SELECT COUNT(*) FROM EXITS_90D)                                                                       AS exits_90d_total,
          (SELECT SUM(CASE WHEN TENURE_DAYS<90 THEN 1 ELSE 0 END) FROM EXITS_90D)                                AS exits_90d_early,
          ROUND(100.0*(SELECT SUM(CASE WHEN TENURE_DAYS<90 THEN 1 ELSE 0 END) FROM EXITS_90D)
                /(SELECT COUNT(*) FROM EXITS_90D),1)                                                             AS early_exit_pct_90d,
          (SELECT SUM(CASE WHEN BAND IN ('B4','B5','B6','Builder') THEN 1 ELSE 0 END) FROM EXITS_90D)            AS b4plus_exits_90d,
          (SELECT COUNT(*) FROM ALL_EMP
            WHERE DATE_OF_EXIT BETWEEN DATEADD(month,-12,CURRENT_DATE()) AND CURRENT_DATE()
              AND BAND IN ('B4','B5','B6','Builder'))                                                            AS b4plus_exits_12m
    """,
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
    td        = run_query(cur, SQL["talent_density"])
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

    # Founder-view Talent Density tiles — Snowflake CSPL + CAPL EMPLOYEES (live)
    ov["td_active_hc"]            = int(td["active_hc"] or 0)
    ov["td_builders_b4plus"]      = int(td["builders_b4plus"] or 0)
    ov["td_builder_density_pct"]  = float(td["builder_density_pct"] or 0)
    ov["td_tenure_lt_1y_pct"]     = float(td["tenure_lt_1y_pct"] or 0)
    ov["td_tenure_3y_plus_pct"]   = float(td["tenure_3y_plus_pct"] or 0)
    ov["td_exits_90d_total"]      = int(td["exits_90d_total"] or 0)
    ov["td_early_exits_90d"]      = int(td["exits_90d_early"] or 0)
    ov["td_early_exit_pct_90d"]   = float(td["early_exit_pct_90d"] or 0)
    ov["td_b4plus_exits_90d"]     = int(td["b4plus_exits_90d"] or 0)
    ov["td_b4plus_exits_12m"]     = int(td["b4plus_exits_12m"] or 0)
    ov["td_source"]               = "snowflake"
    ov["td_note"]                 = (
        "Snowflake live · CSPL + CAPL EMPLOYEES (active filter on IS_ACTIVE + EMPLOYEE_STATUS). "
        "Founder-grade talent-density tiles, refreshed daily."
    )

    d["refreshed_at"] = datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime("%d %b %Y · %H:%M IST")
    with open(json_path,"w") as f: json.dump(d,f,indent=2)
    print("Patched:", json_path)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: snowflake_refresh.py <dashboard-data.json>"); sys.exit(2)
    main(sys.argv[1])
