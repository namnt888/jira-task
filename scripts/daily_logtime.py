import json
import logging
import os
import sys
from datetime import datetime, date, timedelta

from jira_client import (
    get_issue, add_worklog, get_tz
)
from notify import send_notification

logger = logging.getLogger(__name__)

SPRINT_CONFIG_PATH = "data/sprint_config.json"
LOG_HISTORY_PATH = "data/log_history.json"
DONE_STATUS_IDS = {"10179", "10040"}
MIN_LOG_SECONDS = 900
ROUND_TO_SECONDS = 900
SAIGON = get_tz()


def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _working_days_between(from_date: date, to_date: date):
    count = 0
    current = from_date
    while current <= to_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _today_str():
    return datetime.now(SAIGON).strftime("%Y-%m-%d")


def run():
    config = _load_json(SPRINT_CONFIG_PATH)
    if not config or "tickets" not in config:
        logger.warning("No sprint config found")
        send_notification("⚠️ Daily log time skipped: no sprint config found")
        return

    sprint_start = config["sprint_start_date"]
    sprint_end = config["sprint_end_date"]
    today_str = _today_str()
    today_date = date.fromisoformat(today_str)

    if today_str < sprint_start or today_str > sprint_end:
        logger.info(f"Today {today_str} is outside sprint {sprint_start} → {sprint_end}, skipping")
        send_notification(f"⏰ Daily Log Time skipped — {today_str} outside sprint ({sprint_start} → {sprint_end})")
        return

    log_history = _load_json(LOG_HISTORY_PATH)
    if not log_history:
        log_history = {"logs": []}

    existing_date_entry = next((e for e in log_history["logs"] if e["date"] == today_str), None)
    if existing_date_entry:
        logger.info(f"Already logged for {today_str}, skipping")
        send_notification(f"⏰ Daily Log Time skipped — already logged for {today_str}")
        return

    end_date = date.fromisoformat(sprint_end)
    remaining_working_days = _working_days_between(today_date, end_date)
    if remaining_working_days <= 0:
        remaining_working_days = 1

    entries = []
    total_logged = 0
    logged_details = []
    skipped_done = []

    for ticket in config["tickets"]:
        for subtask in ticket.get("subtasks", []):
            key = subtask["key"]
            issue = get_issue(key, fields=["timetracking", "status"])
            fields = issue.get("fields", {})
            status_id = fields.get("status", {}).get("id", "")
            timetracking = fields.get("timetracking", {}) or {}
            remaining = timetracking.get("remainingEstimateSeconds", 0)

            if status_id in DONE_STATUS_IDS:
                skipped_done.append(key)
                logger.info(f"{key}: skipping (status done)")
                continue

            if not remaining or remaining <= 0:
                skipped_done.append(key)
                logger.info(f"{key}: skipping (remaining = 0)")
                continue

            daily_seconds = max(
                MIN_LOG_SECONDS,
                round(remaining / remaining_working_days / ROUND_TO_SECONDS) * ROUND_TO_SECONDS
            )

            started = f"{today_str}T09:00:00.000+0700"
            comment = {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Auto-logged by sprint automation"}]
                }]
            }

            add_worklog(key, daily_seconds, started, comment)
            logger.info(f"{key}: logged {daily_seconds}s (remaining was {remaining}s)")

            entries.append({
                "key": key,
                "logged_seconds": daily_seconds,
                "remaining_before": remaining,
                "remaining_after": remaining - daily_seconds,
            })
            total_logged += daily_seconds
            logged_details.append(f"• {key}: +{daily_seconds // 3600}h{(daily_seconds % 3600) // 60}m (remaining: {remaining // 3600}h → {(remaining - daily_seconds) // 3600}h)")

    log_history["logs"].append({
        "date": today_str,
        "entries": entries,
    })
    _save_json(LOG_HISTORY_PATH, log_history)

    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = weekday_names[datetime.now(SAIGON).weekday()]

    notify_lines = [
        f"⏰ Daily Log Time — {today_str} ({weekday})",
        f"📅 Sprint: {remaining_working_days} working days remaining",
        "",
        "Logged:",
    ]
    notify_lines.extend(logged_details)
    if skipped_done:
        notify_lines.append("")
        notify_lines.append("⏭️ Skipped (already Done):")
        for k in skipped_done:
            notify_lines.append(f"• {k}")
    notify_lines.append("")
    notify_lines.append(f"📊 Total logged today: {total_logged // 3600}h{(total_logged % 3600) // 60}m")

    send_notification("\n".join(notify_lines))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run()
