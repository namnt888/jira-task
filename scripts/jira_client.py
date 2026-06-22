import os
import time
import logging
import base64
from datetime import timezone, timedelta, datetime

import requests

logger = logging.getLogger(__name__)

JIRA_BASE_URL = "https://oneline.atlassian.net"
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
API_DELAY = 0.5
MAX_RETRIES = 3

_headers = None
_session = None


def _get_auth_header():
    global _headers
    if _headers is None:
        token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
        _headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return _headers


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(_get_auth_header())
    return _session


def _request(method, path, **kwargs):
    url = f"{JIRA_BASE_URL}{path}"
    session = _get_session()
    timeout = kwargs.pop("timeout", 30)

    for attempt in range(MAX_RETRIES):
        try:
            resp = session.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code == 429:
                wait = (attempt + 1) * 2
                logger.warning(f"Rate limited. Retrying in {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(API_DELAY)
            return resp.json() if resp.text else {}
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = (attempt + 1) * 2
                logger.warning(f"Request failed: {e}. Retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Request failed after {MAX_RETRIES} retries: {e}")
                raise
    return None


def get_issue(key, fields=None):
    params = {}
    if fields:
        params["fields"] = ",".join(fields)
    return _request("GET", f"/rest/api/3/issue/{key}", params=params)


def get_transitions(key):
    return _request("GET", f"/rest/api/3/issue/{key}/transitions")


def do_transition(key, transition_id):
    return _request("POST", f"/rest/api/3/issue/{key}/transitions", json={"transition": {"id": str(transition_id)}})


def update_issue(key, fields):
    return _request("PUT", f"/rest/api/3/issue/{key}", json={"fields": fields})


def add_worklog(key, time_spent_seconds, started, comment=None):
    body = {
        "timeSpentSeconds": int(time_spent_seconds),
        "started": started,
    }
    if comment:
        body["comment"] = comment
    return _request("POST", f"/rest/api/3/issue/{key}/worklog", json=body)


def get_board_sprints(board_id, state="active"):
    return _request("GET", f"/rest/agile/1.0/board/{board_id}/sprint", params={"state": state})


def get_sprint_issues(sprint_id):
    return _request("GET", f"/rest/agile/1.0/sprint/{sprint_id}/issue")


def find_story_points_field(issue):
    fields = issue.get("fields", {})
    for field_name in ["customfield_10016", "customfield_10028"]:
        val = fields.get(field_name)
        if val is not None:
            logger.info(f"Found story points in {field_name}: {val}")
            return field_name, val
    return None, None


def get_tz():
    return timezone(timedelta(hours=7))
