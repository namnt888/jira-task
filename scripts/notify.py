import os
import logging
from datetime import datetime

import requests

from jira_client import get_tz

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("GOOGLE_SPACE_WEBHOOK", "")


def send_notification(message: str):
    timestamp = datetime.now(get_tz()).strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp} Asia/Saigon]\n{message}"

    if not WEBHOOK_URL:
        print(full_message)
        logger.info("GOOGLE_SPACE_WEBHOOK not set; printed to stdout")
        return

    try:
        resp = requests.post(WEBHOOK_URL, json={"text": full_message}, timeout=15)
        resp.raise_for_status()
        logger.info("Notification sent successfully")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send notification: {e}")
