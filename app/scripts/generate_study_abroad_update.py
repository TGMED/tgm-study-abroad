"""Generates a study-abroad/scholarship update and adds it to the admin
approval queue at /admin/updates -- nothing posts to #general on its own;
an admin has to click Approve first.

This app has no built-in job scheduler, so run this manually
(`python scripts/generate_study_abroad_update.py`) or wire it up to an
external scheduler (Windows Task Scheduler, cron, etc.) to run twice a day.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from extensions import get_db  # noqa: E402
from services.gemini import GeminiError  # noqa: E402
from services.study_updates import generate_and_queue_update  # noqa: E402

if __name__ == "__main__":
    with app.app_context():
        db = get_db()
        try:
            queue_id, content = generate_and_queue_update(db)
        except GeminiError as exc:
            print(f"Could not generate an update: {exc}")
            sys.exit(1)
        print(f"Queued update #{queue_id} for admin approval:\n\n{content}")
