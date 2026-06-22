# NCOP Sprint Automation — Claude Code Prompt

Build a GitHub repo called `ncop-sprint-automation` with Python scripts + GitHub Actions workflows to automate Jira sprint management for project **NCOP** (OM-NCOP) on `oneline.atlassian.net`.

## Tech Stack
- **Python 3.12** + `requests` (only dependency)
- **GitHub Actions** for scheduling & manual triggers
- **JSON files in repo** for data persistence (no database)
- **Google Chat Space Webhook** for notifications

## Repo Structure

```
ncop-sprint-automation/
├── .github/
│   └── workflows/
│       ├── sprint-setup.yml          # Manual trigger — paste tickets, config sprint
│       ├── daily-logtime.yml         # Cron 18:00 Mon-Fri (Asia/Saigon)
│       └── sprint-close.yml         # Cron on sprint end date + manual trigger
├── scripts/
│   ├── jira_client.py               # Shared Jira API client
│   ├── sprint_setup.py              # Đánh estimate, map subtasks
│   ├── daily_logtime.py             # Log worklog hàng ngày
│   ├── sprint_close.py              # Close tickets, reset remaining
│   └── notify.py                    # Google Space webhook notification
├── data/
│   ├── sprint_config.json           # Sprint dates, ticket list, config
│   └── log_history.json             # History of daily logs
├── requirements.txt                 # requests
└── README.md                        # Setup guide
```

---

## NCOP Project Configuration (REAL DATA — use exactly as-is)

### Jira Instance
- **Base URL:** `https://oneline.atlassian.net`
- **Project Key:** `NCOP`
- **Project ID:** `10749`

### Boards
- **Main Sprint Board:** ID `948` (scrum) — use this as primary board
- **Testing Board:** ID `5592` (scrum)
- **UAT Board:** ID `1211` (scrum)

### Parent Issue Types (level 0 — these go into sprint)
| Type | ID | Has TESTED status? |
|------|----|--------------------|
| Story | 10001 | ✅ Yes (status ID: 10511) |
| Bug | 10016 | ✅ Yes |
| Task | 10014 | ✅ Yes |
| Enhancement | 10836 | ✅ Yes |
| Work | 11343 | ✅ Yes |
| Improvement | 10792 | ✅ Yes |
| Overhead | 10418 | ✅ Yes |
| NFR | 11136 | ✅ Yes |
| Tech Solution | 10417 | ✅ Yes |
| Legacy Bug | 10383 | ✅ Yes |
| Release Work | 10799 | ✅ Yes |

### Subtask Types (level -1 — children of parent issues)
| Type | ID | Done Status |
|------|----|----|
| Sub-Test | 10380 | Done (ID: 10179) |
| Sub-Imp | 10379 | Done (ID: 10179) |
| Sub-Bug | 10381 | Done (ID: 10179) |
| Sub-Legacy Bug | 10384 | Done (ID: 10179) |
| Sub PML | 10795 | Done (ID: 10179) |
| Sub Ritual | 10797 | Done (ID: 10179) |
| Sub Overhead | 10796 | Done (ID: 10179) |
| Sub-Refinement | 10793 | Done (ID: 10179) |
| Sub-Env and SCM | 10419 | Done (ID: 10179) |
| Sub Test Execution | 10314 | Done (ID: 10179) |
| Sub-TA-Task | 11380 | Done (ID: 10179) |
| Sub Project Kaizen | 12294 | Done (ID: 10179) |
| Sub Skill Up | 12295 | Done (ID: 10179) |

### Parent Issue Statuses (Lean Agile Workflow)
**In Progress statuses (yellow):**
- `TO DO` (ID: 10001) — category: To Do
- `IN BUSINESS REFINEMENT` (ID: 10503)
- `Business Refinement Done` (ID: 10504)
- `IN TECHNICAL SOLUTION` (ID: 10505)
- `TECHNICAL SOLUTION DONE` (ID: 10506)
- `READY FOR DEVELOPMENT` (ID: 10507)
- `IN DEVELOPMENT` (ID: 10508)
- `DEVELOPED` (ID: 10509)
- `IN QA` (ID: 10510)

**Done statuses (green) — DO NOT transition these:**
- `TESTED` (ID: 10511) ← **TARGET status for sprint close**
- `DEMONSTRATED` (ID: 10512)
- `PO ACCEPTED` (ID: 25513)
- `Accepted` (ID: 10046)
- `IN UAT` (ID: 10275)
- `IN PRODUCTION` (ID: 10514)
- `Cancelled` (ID: 10040)

### Subtask Statuses
**In Progress:**
- `TO DO` (ID: 10001)
- `In Progress` (ID: 10420)
- `AVAILABLE FOR CODE REVIEW` (ID: 10515)
- `IN CODE REVIEW` (ID: 10516)
- `AVAILABLE FOR RETEST` (ID: 10517) — Sub-Bug, Sub-Legacy Bug only
- `IN RETEST` (ID: 10518) — Sub-Bug, Sub-Legacy Bug only

**Done:**
- `Done` (ID: 10179) ← **TARGET status for subtask close**
- `Cancelled` (ID: 10040)

---

## GitHub Secrets Required
```
JIRA_EMAIL          — Jira account email
JIRA_API_TOKEN      — Jira API token from https://id.atlassian.com/manage-profile/security/api-tokens
GOOGLE_SPACE_WEBHOOK — Google Chat Space webhook URL
```

---

## Feature 1: Sprint Setup (`sprint-setup.yml`)

### Trigger
`workflow_dispatch` with these inputs:
```yaml
inputs:
  ticket_keys:
    description: 'Paste ticket keys (comma or newline separated, e.g. NCOP-1234,NCOP-1235)'
    required: true
    type: string
  sprint_start_date:
    description: 'Sprint start date (YYYY-MM-DD)'
    required: true
    type: string
  sprint_end_date:
    description: 'Sprint end date (YYYY-MM-DD)'
    required: true
    type: string
  hours_per_point:
    description: 'Hours per story point (default: 8)'
    required: false
    default: '8'
    type: string
  assignee_account_id:
    description: 'Jira account ID of the person to log time for'
    required: true
    type: string
```

### Logic (`sprint_setup.py`)

1. **Parse ticket keys** from input (handle comma, newline, space separated)

2. **For each parent ticket:**
   a. Call `GET /rest/api/3/issue/{key}` to get:
      - Story points (field: `customfield_10016` — standard Jira story points, but discover the correct field by checking the issue response)
      - Current subtasks list
   b. **Calculate total estimate** = story_points × hours_per_point (in seconds for API)
   c. **Map subtasks and distribute estimate:**
      - Find `Sub-Test` subtasks → allocate **30%** of total estimate
      - Remaining subtasks → distribute remaining **70%** equally
      - If no Sub-Test exists, distribute equally among all subtasks
      - If no subtasks exist, set estimate on parent ticket only
   d. **Set original estimate** on each subtask via:
      ```
      PUT /rest/api/3/issue/{subtaskKey}
      Body: {"fields": {"timetracking": {"originalEstimate": "{hours}h"}}}
      ```
   e. Also set original estimate on parent ticket (sum of all subtask estimates, or full estimate if no subtasks)

3. **Save sprint config** to `data/sprint_config.json`:
   ```json
   {
     "sprint_start_date": "2026-06-22",
     "sprint_end_date": "2026-07-03",
     "hours_per_point": 8,
     "assignee_account_id": "712020:87961eb1-cf4e-4c0a-b8d8-6ad8c061f0c4",
     "tickets": [
       {
         "key": "NCOP-1234",
         "story_points": 3,
         "total_estimate_hours": 24,
         "subtasks": [
           {"key": "NCOP-1235", "type": "Sub-Test", "estimate_hours": 7.2},
           {"key": "NCOP-1236", "type": "Sub-Imp", "estimate_hours": 16.8}
         ]
       }
     ],
     "created_at": "2026-06-22T09:00:00+07:00"
   }
   ```

4. **Git commit** the updated `data/sprint_config.json`

5. **Send Google Space notification:**
   ```
   🚀 Sprint Setup Complete
   📅 2026-06-22 → 2026-07-03
   📊 X tickets configured, Y subtasks estimated
   ⏱️ Total estimate: Z hours (1 point = 8h)
   
   Tickets:
   • NCOP-1234 (3pts → 24h): Sub-Test 7.2h, Sub-Imp 16.8h
   • NCOP-1235 (5pts → 40h): Sub-Test 12h, Sub-Imp 14h, Sub-Imp 14h
   ```

---

## Feature 2: Daily Log Time (`daily-logtime.yml`)

### Trigger
```yaml
on:
  schedule:
    # Run at 18:00 Vietnam time (11:00 UTC) Mon-Fri
    - cron: '0 11 * * 1-5'
  workflow_dispatch:  # Manual trigger for testing
```

### Logic (`daily_logtime.py`)

1. **Load** `data/sprint_config.json`

2. **Check if today is within sprint dates** (use Asia/Saigon timezone). If not, skip and notify.

3. **For each subtask in config:**
   a. Call `GET /rest/api/3/issue/{subtaskKey}` to get:
      - `timetracking.remainingEstimateSeconds`
      - Current status
   b. **Skip if:**
      - Status is `Done` (10179) or `Cancelled` (10040)
      - Remaining estimate is 0 or null
   c. **Calculate daily log amount:**
      - Count remaining **working days** from today to sprint_end_date (Mon-Fri only, exclude weekends)
      - `daily_log_seconds = remainingEstimateSeconds / remaining_working_days`
      - Round to nearest 15 minutes (900 seconds)
      - Minimum log: 15 minutes (900 seconds)
   d. **Add worklog:**
      ```
      POST /rest/api/3/issue/{subtaskKey}/worklog
      Body: {
        "timeSpentSeconds": daily_log_seconds,
        "started": "2026-06-22T09:00:00.000+0700",
        "comment": {
          "type": "doc",
          "version": 1,
          "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Auto-logged by sprint automation"}]}]
        }
      }
      ```
      - Use `started` = today at 09:00 Asia/Saigon
      - The `started` field format must be: `YYYY-MM-DDThh:mm:ss.SSS+0700`

4. **Update log history** in `data/log_history.json`:
   ```json
   {
     "logs": [
       {
         "date": "2026-06-22",
         "entries": [
           {"key": "NCOP-1235", "logged_seconds": 3600, "remaining_before": 28800, "remaining_after": 25200},
           {"key": "NCOP-1236", "logged_seconds": 7200, "remaining_before": 57600, "remaining_after": 50400}
         ]
       }
     ]
   }
   ```

5. **Git commit** updated `data/log_history.json`

6. **Send Google Space notification:**
   ```
   ⏰ Daily Log Time — 22/06/2026 (Mon)
   📅 Sprint: 5 working days remaining
   
   Logged:
   • NCOP-1235 (Sub-Test): +1h (remaining: 7h → 6h)
   • NCOP-1236 (Sub-Imp): +2h (remaining: 14h → 12h)
   
   ⏭️ Skipped (already Done):
   • NCOP-1237 (Sub-Refinement)
   
   📊 Total logged today: 3h
   ```

---

## Feature 3: Sprint Close (`sprint-close.yml`)

### Trigger
```yaml
on:
  schedule:
    # Run at 17:00 Vietnam time (10:00 UTC) every weekday
    # Script will check if today == sprint_end_date
    - cron: '0 10 * * 1-5'
  workflow_dispatch:  # Manual trigger anytime
    inputs:
      force_run:
        description: 'Force run even if not sprint end date'
        required: false
        default: 'false'
        type: boolean
      dry_run:
        description: 'Dry run — show what would happen without making changes'
        required: false
        default: 'false'
        type: boolean
```

### Logic (`sprint_close.py`)

1. **Load** `data/sprint_config.json`

2. **Check if today == sprint_end_date** (or force_run is true). If not, exit silently.

3. **For each parent ticket in config:**

   a. **Process subtasks first:**
      - Get each subtask's current status
      - If status is NOT in done category (`Done` 10179, `Cancelled` 10040):
        - Get available transitions: `GET /rest/api/3/issue/{key}/transitions`
        - Find transition that leads to `Done` (status ID 10179)
        - Execute transition: `POST /rest/api/3/issue/{key}/transitions` with `{"transition": {"id": "TRANSITION_ID"}}`
      - Set remaining estimate to 0:
        ```
        PUT /rest/api/3/issue/{key}
        Body: {"fields": {"timetracking": {"remainingEstimate": "0h"}}}
        ```

   b. **Process parent ticket:**
      - Get current status
      - If status is NOT in done category (`TESTED` 10511, `DEMONSTRATED` 10512, `PO ACCEPTED` 25513, `Accepted` 10046, `IN UAT` 10275, `IN PRODUCTION` 10514, `Cancelled` 10040):
        - Get available transitions: `GET /rest/api/3/issue/{key}/transitions`
        - Find transition that leads to `TESTED` (status ID 10511)
        - If direct transition exists → execute it
        - If NOT → log warning, skip this ticket (don't force invalid transitions)
      - Set remaining estimate to 0

4. **Handle errors gracefully:**
   - If a transition fails (e.g., workflow doesn't allow it), log the error and continue with next ticket
   - Collect all errors and include in notification

5. **Send Google Space notification:**
   ```
   🏁 Sprint Close — Sprint 22/06 → 03/07/2026
   
   ✅ Subtasks → Done: 15 tickets
   ✅ Parents → TESTED: 8 tickets
   ✅ Remaining reset to 0: 23 tickets
   
   ⚠️ Could not transition (workflow restriction):
   • NCOP-1234: Status "TO DO" → no direct path to TESTED
   
   ⏭️ Already done (skipped): 5 tickets
   ```

   If dry_run:
   ```
   🔍 Sprint Close DRY RUN — Sprint 22/06 → 03/07/2026
   
   Would transition subtasks → Done: 15 tickets
   Would transition parents → TESTED: 8 tickets
   Would reset remaining: 23 tickets
   
   ⚠️ Cannot transition:
   • NCOP-1234: Status "TO DO" → no direct path to TESTED
   ```

---

## Shared Module: `jira_client.py`

```python
"""
Shared Jira API client.
- Base URL: https://oneline.atlassian.net
- Auth: Basic auth (email + API token)
- Rate limiting: respect 429 responses with exponential backoff
- Timeout: 30 seconds per request
"""
```

Key methods:
- `get_issue(key, fields=None)` — GET /rest/api/3/issue/{key}
- `get_transitions(key)` — GET /rest/api/3/issue/{key}/transitions
- `do_transition(key, transition_id)` — POST /rest/api/3/issue/{key}/transitions
- `update_issue(key, fields)` — PUT /rest/api/3/issue/{key}
- `add_worklog(key, time_spent_seconds, started, comment=None)` — POST /rest/api/3/issue/{key}/worklog
- `get_board_sprints(board_id, state="active")` — GET /rest/agile/1.0/board/{boardId}/sprint
- `get_sprint_issues(sprint_id)` — GET /rest/agile/1.0/sprint/{sprintId}/issue

Include:
- Retry logic with exponential backoff (3 retries)
- Proper error handling and logging
- Rate limit handling (429 status)

---

## Shared Module: `notify.py`

Send notifications to Google Chat Space via webhook:

```python
"""
POST to Google Space webhook URL.
Content-Type: application/json
Body: {"text": "message"}

For rich formatting, use simple markdown:
- *bold*
- `code`
- Newlines with \n
"""
```

- Read webhook URL from env var `GOOGLE_SPACE_WEBHOOK`
- If webhook URL is not set, print to stdout instead (for local testing)
- Include timestamp in Asia/Saigon timezone

---

## GitHub Actions Workflow Details

### All workflows should:
1. Use `actions/checkout@v4` with `token: ${{ secrets.GITHUB_TOKEN }}`
2. Set up Python 3.12 with `actions/setup-python@v5`
3. Install requirements: `pip install -r requirements.txt`
4. Set environment variables from secrets
5. After script runs, **auto-commit** any changes to `data/` folder:
   ```yaml
   - name: Commit data changes
     run: |
       git config user.name "Sprint Automation Bot"
       git config user.email "bot@ncop-automation.local"
       git add data/
       git diff --staged --quiet || git commit -m "chore: update sprint data [skip ci]"
       git push
   ```

### Permissions
```yaml
permissions:
  contents: write  # For committing data files
```

---

## README.md Content

Include:
1. What this repo does (3 features summary)
2. Prerequisites (Python 3.12, Jira API token, Google Space webhook)
3. Setup steps:
   - Fork/clone repo
   - Add GitHub Secrets (JIRA_EMAIL, JIRA_API_TOKEN, GOOGLE_SPACE_WEBHOOK)
   - Run Sprint Setup workflow manually
4. How each workflow works
5. How to run locally for testing
6. Troubleshooting common issues (transition failures, rate limits)

---

## Important Implementation Notes

1. **Timezone:** All date/time operations must use `Asia/Saigon` (UTC+7). Python's `datetime` with `timezone(timedelta(hours=7))`.

2. **Working days calculation:** Only count Mon-Fri. Do NOT count weekends. Do NOT account for Vietnamese holidays (keep it simple).

3. **Story points field:** The field name for story points varies. Try `customfield_10016` first. If not found, check `customfield_10028` (story point estimate). Log which field was used.

4. **Transition discovery:** ALWAYS use `GET /rest/api/3/issue/{key}/transitions` to discover available transitions. NEVER hardcode transition IDs — they vary by issue type and current status.

5. **Idempotency:** 
   - Daily log: Check `data/log_history.json` to avoid double-logging on the same date
   - Sprint close: Skip tickets already in done status

6. **Error handling:** Never let one ticket failure stop the entire batch. Process all tickets, collect errors, report in notification.

7. **Git commit:** Use `[skip ci]` in commit message to avoid triggering workflows recursively.

8. **Jira API auth:** Basic auth with base64 encoded `email:api_token`.

9. **Worklog `started` field:** Must be in ISO 8601 format with timezone offset: `2026-06-22T09:00:00.000+0700`. The `+0700` is for Asia/Saigon.

10. **Rate limiting:** Jira Cloud allows ~100 requests per minute. Add 0.5s delay between API calls to be safe.
