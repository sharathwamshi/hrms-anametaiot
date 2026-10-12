"""Best-effort push notifications via Expo's push service. Expo's service
routes to both APNs and FCM for us, so there's no Firebase project or Apple
push certificate to manage on this backend — just POST the Expo push tokens
registered by the mobile app.

Sending never raises: a push failure must never break the API call it's
attached to (e.g. approving a regularization request still succeeds even if
the push itself fails or Expo's service is unreachable).
"""
import logging
import requests
from flask import current_app

from app.extensions import db
from app.models import DeviceToken

logger = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(user_ids, title, body, data=None):
    """Push `title`/`body` to every device registered to any of `user_ids`.
    `user_ids` may be a single id or a list. Silently does nothing if push is
    disabled, the user has no registered device, or sending fails."""
    if not user_ids:
        return
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    if not current_app.config.get("EXPO_PUSH_ENABLED", True):
        logger.info("Push disabled — would have sent %r to users %s", title, user_ids)
        return

    tokens = [t.token for t in DeviceToken.query.filter(DeviceToken.user_id.in_(user_ids)).all()]
    if not tokens:
        return

    messages = [{"to": tok, "title": title, "body": body, "data": data or {}, "sound": "default"} for tok in tokens]
    try:
        requests.post(EXPO_PUSH_URL, json=messages, timeout=5,
                       headers={"Content-Type": "application/json", "Accept": "application/json"})
    except Exception:
        logger.exception("Push send failed for users %s", user_ids)
