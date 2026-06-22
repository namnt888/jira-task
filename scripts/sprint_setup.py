import json
import logging
import sys
from datetime import datetime

from jira_client import (
    get_issue, update_issue, find_story_points_field, get_tz
)
from notify import send_notification

logger = logging.getLogger(__name__)

SPRINT_CONFIG_PATH = "data/sprint_config.json"

SUBTASK_ESTIMATE_SUB_TEST_RATIO = 0.30
SECONDS_PER_HOUR = 3600


def _parse_ticket_keys(raw: str):
    import re
    keys = re.split(r"[,;\s\n]+", raw.strip())
    return [k.strip().upper() for k in keys if k.strip()]


def _distribute_estimate(total_hours: float, subtasks: list):
    if not subtasks:
        return [], total_hours

    is_sub_test = [s for s in subtasks if s.get("type_name", "").lower() == "sub-test"]
    others = [s for s in subtasks if s.get("type_name", "").lower() != "sub-test"]

    result = []
    if is_sub_test:
        sub_test_total = total_hours * SUBTASK_ESTIMATE_SUB_TEST_RATIO
        per_sub_test = round(sub_test_total / len(is_sub_test), 2)
        for s in is_sub_test:
            result.append({"key": s["key"], "type": s["type_name"], "estimate_hours": per_sub_test})
        remaining = total_hours * (1 - SUBTASK_ESTIMATE_SUB_TEST_RATIO)
        if others:
            per_other = round(remaining / len(others), 2)
            for s in others:
                result.append({"key": s["key"], "type": s["type_name"], "estimate_hours": per_other})
    else:
        per_sub = round(total_hours / len(subtasks), 2)
        for s in subtasks:
            result.append({"key": s["key"], "type": s["type_name"], "estimate_hours": per_sub})

    return result, total_hours


def _set_original_estimate(key: str, hours: float):
    hours_str = f"{hours}h"
    update_issue(key, {"timetracking": {"originalEstimate": hours_str}})
    logger.info(f"Set estimate on {key}: {hours_str}")


def run(ticket_keys_raw: str, sprint_start: str, sprint_end: str,
        hours_per_point: int, assignee_account_id: str):
    keys = _parse_ticket_keys(ticket_keys_raw)
    logger.info(f"Processing {len(keys)} ticket(s): {keys}")

    tickets_config = []
    total_hours_all = 0.0
    for key in keys:
        issue = get_issue(key)
        fields = issue.get("fields", {})
        field_name, story_points = find_story_points_field(issue)
        if story_points is None:
            logger.warning(f"No story points found for {key}, defaulting to 0")
            story_points = 0

        total_estimate_hours = story_points * hours_per_point
        existing_subtasks = fields.get("subtasks", [])

        subtask_list = []
        for st in existing_subtasks:
            st_key = st.get("key", "")
            st_issue = get_issue(st_key)
            st_fields = st_issue.get("fields", {})
            st_type = st_fields.get("issuetype", {})
            subtask_list.append({
                "key": st_key,
                "type_name": st_type.get("name", ""),
                "type_id": st_type.get("id", ""),
            })

        estimated_subtasks, parent_hours = _distribute_estimate(total_estimate_hours, subtask_list)
        subtask_total = sum(s["estimate_hours"] for s in estimated_subtasks)

        for st in estimated_subtasks:
            _set_original_estimate(st["key"], st["estimate_hours"])

        if estimated_subtasks:
            _set_original_estimate(key, subtask_total)
        else:
            _set_original_estimate(key, parent_hours)

        total_hours_all += parent_hours

        tickets_config.append({
            "key": key,
            "story_points": story_points,
            "total_estimate_hours": total_estimate_hours,
            "subtasks": estimated_subtasks,
        })
        logger.info(f"{key}: {story_points}pts -> {total_estimate_hours}h ({len(estimated_subtasks)} subtasks)")

    config = {
        "sprint_start_date": sprint_start,
        "sprint_end_date": sprint_end,
        "hours_per_point": hours_per_point,
        "assignee_account_id": assignee_account_id,
        "tickets": tickets_config,
        "created_at": datetime.now(get_tz()).isoformat(),
    }

    with open(SPRINT_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Saved sprint config to {SPRINT_CONFIG_PATH}")

    notify_lines = [
        "🚀 Sprint Setup Complete",
        f"📅 {sprint_start} → {sprint_end}",
        f"📊 {len(tickets_config)} tickets configured, {sum(len(t['subtasks']) for t in tickets_config)} subtasks estimated",
        f"⏱️ Total estimate: {total_hours_all}h (1 point = {hours_per_point}h)",
        "",
        "Tickets:",
    ]
    for t in tickets_config:
        subs = ", ".join(f"{s['type']} {s['estimate_hours']}h" for s in t["subtasks"])
        if not subs:
            subs = "no subtasks"
        notify_lines.append(f"• {t['key']} ({t['story_points']}pts → {t['total_estimate_hours']}h): {subs}")

    send_notification("\n".join(notify_lines))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run(
        ticket_keys_raw=sys.argv[1],
        sprint_start=sys.argv[2],
        sprint_end=sys.argv[3],
        hours_per_point=int(sys.argv[4]),
        assignee_account_id=sys.argv[5],
    )
