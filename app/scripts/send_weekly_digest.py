"""Sends the weekly community-activity digest to every onboarded member.

This app has no built-in job scheduler, so run this manually
(`python scripts/send_weekly_digest.py`) or wire it up to an external
scheduler (cron, Windows Task Scheduler, Railway/Render cron job, etc.) to
run it automatically once a week.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from extensions import get_db  # noqa: E402
from services.digest import send_weekly_digest  # noqa: E402

if __name__ == "__main__":
    with app.app_context():
        db = get_db()
        community_url = os.environ.get("COMMUNITY_URL", "http://localhost:5000/community")
        sent, skipped, highlights = send_weekly_digest(db, community_url)
        if not highlights:
            print("No community activity in the last 7 days — nothing to send.")
        else:
            print(f"Weekly digest: sent to {sent} member(s), skipped {skipped}.")
