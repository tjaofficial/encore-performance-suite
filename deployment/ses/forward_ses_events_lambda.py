"""AWS Lambda (Python 3.12+) SNS subscriber for Encore SES email events.

Environment:
  ENCORE_EMAIL_EVENT_URL=https://your-encore-domain/communications/email-events/
  ENCORE_EMAIL_EVENT_SECRET=long random secret (same as Django app)

Create SNS subscription to this Lambda; invoke permission should be scoped to
SNS topic ARN. Accept only SNS notifications invoked by AWS, not public HTTP.
"""
import json
import os
import urllib.request


def lambda_handler(event, context):
    url = os.environ["ENCORE_EMAIL_EVENT_URL"]
    secret = os.environ["ENCORE_EMAIL_EVENT_SECRET"]
    forwarded = 0
    for record in event.get("Records", []):
        if record.get("EventSource") != "aws:sns":
            continue
        message = record.get("Sns", {}).get("Message", "")
        parsed = json.loads(message)
        if not isinstance(parsed, dict) or not parsed.get("mail", {}).get("messageId"):
            continue
        if not (parsed.get("eventType") or parsed.get("notificationType")):
            continue
        request = urllib.request.Request(
            url, data=json.dumps(parsed).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "X-Encore-Email-Event-Secret": secret},
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Encore event receiver returned {response.status}")
        forwarded += 1
    return {"forwarded": forwarded}
