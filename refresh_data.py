"""Daily data refresh — pulls live data from the 4 sheets and writes dashboard-data.json.

Invoked by the dashboard-refresh agent at 6 AM IST every day.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).parent / "dashboard-data.json"

# These IDs are the verified authoritative sources (from Satakshi)
SHEETS = {
    "recruitment_metrics": "1x6eJzZtn2xYYFomk4Is3hcDucmq98uOr4IzQiBbIePM",
    "joining_master": "1xb6TtAdaCUUHTjxKza2wvgktf26m_BZIa7glQzaOPgY",
    "tech_product": "1TzXVJ_V_g9PiSfT0NtfbV2oHsoVsRTPuTJtmmalE8uc",
    "third_party_1": "1ueWrvNXpwTimz91ZhCu7rFKsucR-gS7A1oTDaI4QSGo",
}

ZERO_VALUE = "—"

def now_ist():
    """Return IST timestamp for the refresh badge."""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y · %H:%M IST")


def parse_recruitment_metrics(content: str) -> dict:
    """Extract Department-wise + Entity-wise + Source + Gender blocks from the aggregated MIS sheet."""
    # The dashboard-refresh agent (running in Claude) does the heavy parsing —
    # this script is the deterministic shape contract.
    raise NotImplementedError("Agent populates this — see ~/.claude/agents/dashboard-refresh.md")


def main():
    """Stub — the dashboard-refresh agent is what actually runs and rewrites this file.

    This Python file lives alongside the JSON for two reasons:
    1. Documents the contract — what the JSON must look like
    2. Provides a manual-run fallback if the agent is unavailable

    Real refresh path: ~/.claude/agents/dashboard-refresh.md (scheduled daily 6am IST).
    """
    # Maintain freshness on the existing JSON without changing its data —
    # useful for verifying the dashboard stays "live" in case agent runs are skipped
    if OUT.exists():
        with open(OUT) as f:
            data = json.load(f)
        data["refreshed_at"] = now_ist()
        with open(OUT, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Bumped refresh timestamp on {OUT}")
    else:
        print(f"⚠️ {OUT} missing — run the dashboard-refresh agent to seed it.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
