# Encore delivery events: SES → SNS → Lambda → Encore

1. Deploy the updated Django code and migrate `communications` first.
2. In AWS **us-east-2** (or the exact `AWS_SES_REGION` configured in Encore), open **Amazon SNS**, create a **Standard** topic named `encore-email-events`.
3. In **AWS Lambda**, create a Python 3.12+ function `encore-forward-email-events`; paste `forward_ses_events_lambda.py` and set handler `forward_ses_events_lambda.lambda_handler`. Set timeout 20 seconds.
4. Lambda environment variables:
   - `ENCORE_EMAIL_EVENT_URL`: `https://YOUR_DOMAIN/communications/email-events/` (check against your Django URL prefix; `communications/urls.py` declares `email-events/`)
   - `ENCORE_EMAIL_EVENT_SECRET`: securely generated 32+ byte random value. The identical value must be in the **Django container environment**. Do not store this value in git or screenshot it.
5. Subscribe Lambda to the SNS topic under SNS → Topic → Create subscription → AWS Lambda; confirm Lambda has a resource-based permission allowing invocation by that **specific SNS Topic ARN**.
6. Open SES → Configuration → Configuration sets → `encore-main` → Event destinations → Add destination. Enable **Send, Delivery, Hard bounce, Complaint, Reject, Delivery delay, Rendering failure** when supported; choose **Amazon SNS** and the topic above. All outbound messages must send with `SES_CONFIGURATION_SET=encore-main`.
7. Ensure SES/SNS topic access policy allows SES to publish from your AWS account/configuration set. Keep this narrow, per AWS docs. If Lambda is in a private VPC, provide outgoing HTTPS access to Encore.
8. Send a test email to a verified test mailbox. Confirm `OutboundEmailLog` goes from Accepted to Delivered and has the event timeline. A successful API call alone only means Accepted.
9. Monitor CloudWatch Logs for `encore-forward-email-events` and Lambda retry/dead-letter behavior; enable an alarm for failures. Never configure SNS to POST directly to the Django endpoint with a shared-secret header, because SNS cannot provide this header and the receiver intentionally refuses unsigned requests.

The app's receiving endpoint uses a shared secret; TLS is required. For production-grade security, restrict source ingress where possible, use a secret manager, and periodically rotate the shared secret.
