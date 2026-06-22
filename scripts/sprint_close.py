import json
import logging
import os
import sys
from datetime import date

from jira_client import (
    get_issue, get_transitions, do_transition, update_issue, get_tz
)
from notify import send_notification

logger = logging.getLogger(__name__)

SPRINT_CONFIG_PATH = "data/sprint_config.json"

SUBTASK_DONE_STATUS_IDS = {"10179", "10040"}
SUBTASK_DONE_TARGET_ID = "10179"
PARENT_DONE_STATUS_IDS = {
    "10511",  # TESTED
    "10512",  # DEMONSTRATED
    "25513",  # PO ACCEPTED
    "10046",  # Accepted
    "10275",  # IN UAT
    "10514",  # IN PRODUCTION
    "10040",  # Cancelled
}
PARENT_TARGET_STATUS_ID = "10511"  # TESTED
SAIGON = get_tz()


def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _find_transition_to(transitions_data, target_status_id):
    transitions = transitions_data.get("transitions", [])
    for t in transitions:
        to_status = t.get("to", {})
        if str(to_status.get("id", "")) == str(target_status_id):
            return t.get("id")
    return None


def _reset_remaining(key: str):
    update_issue(key, {"timetracking": {"remainingEstimate": "0h"}})
    logger.info(f"Reset remaining estimate on {key} to 0h")


def _transition_if_possible(key: str, target_status_id: str):
    try:
        transitions = get_transitions(key)
        tid = _find_transition_to(transitions, target_status_id)
        if tid:
            do_transition(key, tid)
            logger.info(f"{key}: transitioned to status {target_status_id}")
            return True, None
        else:
            msg = f"No direct transition path to status {target_status_id}"
            logger.warning(f"{key}: {msg}")
            return False, msg
    except Exception as e:
        logger.error(f"{key}: transition failed: {e}")
        return False, str(e)


def run(force_run=False, dry_run=False):
    config = _load_json(SPRINT_CONFIG_PATH)
    if not config or "tickets" not in config:
        logger.warning("No sprint config found")
        send_notification("⚠️ Sprint close skipped: no sprint config found")
        return

    sprint_end = config["sprint_end_date"]
    today_str = date.today().isoformat()

    if today_str != sprint_end and not force_run:
        logger.info(f"Today {today_str} != sprint end {sprint_end}, skipping (use force_run)")
        return

    dry_run_label = "DRY RUN — " if dry_run else ""
    subtask_done_count = 0
    parent_done_count = 0
    reset_count = 0
    already_done_subtasks = 0
    already_done_parents = 0
    errors = []

    for ticket in config["tickets"]:
        key = ticket["key"]

        for subtask in ticket.get("subtasks", []):
            sk = subtask["key"]
            try:
                issue = get_issue(sk, fields=["status"])
                status_id = issue.get("fields", {}).get("status", {}).get("id", "")

                if status_id in SUBTASK_DONE_STATUS_IDS:
                    already_done_subtasks += 1
                    continue

                if not dry_run:
                    success, err = _transition_if_possible(sk, SUBTASK_DONE_TARGET_ID)
                    if success:
                        subtask_done_count += 1
                    else:
                        errors.append(f"{sk}: {err}")
                    _reset_remaining(sk)
                    reset_count += 1
                else:
                    subtask_done_count += 1
                    reset_count += 1
            except Exception as e:
                errors.append(f"{sk}: {e}")

        try:
            issue = get_issue(key, fields=["status"])
            status_id = issue.get("fields", {}).get("status", {}).get("id", "")

            if status_id in PARENT_DONE_STATUS_IDS:
                already_done_parents += 1
                continue

            if not dry_run:
                success, err = _transition_if_possible(key, PARENT_TARGET_STATUS_ID)
                if success:
                    parent_done_count += 1
                else:
                    errors.append(f"{key}: {err}")
                _reset_remaining(key)
                reset_count += 1
            else:
                parent_done_count += 1
                reset_count += 1
        except Exception as e:
            errors.append(f"{key}: {e}")

    sprint_label = f"Sprint {config['sprint_start_date']} → {sprint_end}"

    notify_lines = [
        f"{'🔍 ' + dry_run_label.strip() if dry_run else '🏁 '}Sprint Close — {sprint_label}",
        "",
    ]

    if dry_run:
        notify_lines.extend([
            f"Would transition subtasks → Done: {subtask_done_count} tickets",
            f"Would transition parents → TESTED: {parent_done_count} tickets",
            f"Would reset remaining: {reset_count} tickets",
        ])
    else:
        notify_lines.extend([
            f"✅ Subtasks → Done: {subtask_done_count} tickets",
            f"✅ Parents → TESTED: {parent_done_count} tickets",
            f"✅ Remaining reset to 0: {reset_count} tickets",
        ])

    already_done_total = already_done_subtasks + already_done_parents
    if already_done_total > 0:
        notify_lines.append(f"")
        notify_lines.append(f"⏭️ Already done (skipped): {already_done_total} tickets")

    if errors:
        notify_lines.append(f"")
        notify_lines.append("⚠️ Errors:")
        for err in errors:
            notify_lines.append(f"• {err}")

    send_notification("\n".join(notify_lines))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    force = "--force" in sys.argv
    dry = "--dry-run" in sys.argv
    run(force_run=force, dry_run=dry)
