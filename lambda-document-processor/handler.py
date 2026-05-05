import json, logging, os, re
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DDB_TABLE_NAME = os.environ["DDB_TABLE_NAME"]
SNS_TOPIC_ARN  = os.environ["SNS_TOPIC_ARN"]

dynamodb = boto3.resource("dynamodb")
textract = boto3.client("textract")
sns      = boto3.client("sns")
table    = dynamodb.Table(DDB_TABLE_NAME)


def lambda_handler(event, context):
    log.info("Event: %s", json.dumps(event))
    for record in event.get("Records", []):
        try:
            process_record(record)
        except Exception:
            log.exception("Failed to process record")
    return {"statusCode": 200}


def process_record(record):
    bucket = record["s3"]["bucket"]["name"]
    key    = record["s3"]["object"]["key"]
    parts  = key.split("/")

    if len(parts) < 3 or parts[0] != "uploads":
        log.warning("Unexpected key format: %s", key)
        return

    application_id = parts[1]

    try:
        resp = textract.detect_document_text(
            Document={"S3Object": {"Bucket": bucket, "Name": key}}
        )
    except ClientError as e:
        log.exception("Textract failed")
        _update_status(application_id, "extraction_failed", error=str(e))
        return

    lines     = [b["Text"] for b in resp.get("Blocks", []) if b["BlockType"] == "LINE"]
    full_text = "\n".join(lines)

    extracted = {
        "applicant_name":         _find(full_text, r"(?:applicant|company|business)\s*name[:\s]+(.+)"),
        "requested_credit_limit": _find(full_text, r"credit\s+(?:limit|amount)[:\s]+\$?([\d,]+)"),
        "industry":               _find(full_text, r"industry[:\s]+(.+)"),
        "raw_text_preview":       full_text[:500],
    }

    _update_application(application_id, extracted)
    _notify(application_id, extracted)


def _find(text, pattern):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _update_application(application_id, fields):
    now = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={"application_id": application_id},
        UpdateExpression="SET #s = :s, updated_at = :u, extracted_fields = :f",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "pending_review", ":u": now, ":f": fields},
    )


def _update_status(application_id, status, error=None):
    now  = datetime.now(timezone.utc).isoformat()
    expr = "SET #s = :s, updated_at = :u"
    vals = {":s": status, ":u": now}
    if error:
        expr += ", error_message = :e"
        vals[":e"] = error[:1000]
    table.update_item(
        Key={"application_id": application_id},
        UpdateExpression=expr,
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues=vals,
    )


def _notify(application_id, extracted):
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"[CreditFlow] Application {application_id[:8]} ready for review",
        Message=(
            f"New credit application ready for review.\n\n"
            f"ID: {application_id}\n"
            f"Applicant: {extracted.get('applicant_name', '(not extracted)')}\n"
            f"Requested limit: {extracted.get('requested_credit_limit', '(not extracted)')}\n"
        ),
    )
