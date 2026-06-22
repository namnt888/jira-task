# NCOP Sprint Automation

Automate Jira sprint management for project NCOP (OM-NCOP) on `oneline.atlassian.net`.

## Features

1. **Sprint Setup** — Parse tickets, calculate estimates, distribute to subtasks, save config
2. **Daily Log Time** — Auto-log worklog daily (Mon-Fri) based on remaining estimates
3. **Sprint Close** — Transition subtasks → Done, parents → TESTED, reset remaining

## Prerequisites

- Python 3.12
- Jira API token from https://id.atlassian.com/manage-profile/security/api-tokens
- Google Chat Space webhook URL (optional — falls back to stdout)

## Setup

1. Clone the repo
2. Add GitHub Secrets:
   - `JIRA_EMAIL` — Jira account email
   - `JIRA_API_TOKEN` — Jira API token
   - `GOOGLE_SPACE_WEBHOOK` — Google Chat Space webhook URL
3. Run the **Sprint Setup** workflow manually with ticket keys, dates, and assignee

## Workflows

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `sprint-setup.yml` | Manual (`workflow_dispatch`) | Configure sprint, estimate tickets |
| `daily-logtime.yml` | Cron 18:00 Mon-Fri + manual | Log daily worklog |
| `sprint-close.yml` | Cron 17:00 Mon-Fri + manual | Close sprint, transition statuses |

## Local Testing

```bash
pip install -r requirements.txt
export JIRA_EMAIL="your@email.com"
export JIRA_API_TOKEN="your-token"
python scripts/sprint_setup.py "NCOP-1234,NCOP-1235" "2026-06-22" "2026-07-03" 8 "712020:..."
```

## Troubleshooting

- **Transition failures:** Workflow rules may prevent direct transitions. Check Jira workflow configuration.
- **Rate limits:** Jira Cloud allows ~100 req/min. Script adds 0.5s delay between calls.
- **Story points not found:** The script tries `customfield_10016` and `customfield_10028`. Verify field IDs in your Jira instance.
