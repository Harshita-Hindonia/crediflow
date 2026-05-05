import os
import logging
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from flask import Flask, jsonify, request
from flask_cors import CORS

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

AWS_REGION       = os.environ.get("AWS_REGION", "us-east-1")
DDB_TABLE_NAME   = os.environ.get("DDB_TABLE_NAME", "creditflow-dev-applications")
S3_BUCKET        = os.environ.get("S3_DOCUMENTS_BUCKET", "creditflow-dev-documents")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")

_dynamodb = None
_s3 = None

def ddb_table():
    global _dynamodb
    if _dynamodb is None:
        kwargs = {"region_name": AWS_REGION}
        if AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = AWS_ENDPOINT_URL
        _dynamodb = boto3.resource("dynamodb", **kwargs)
    return _dynamodb.Table(DDB_TABLE_NAME)

def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "creditflow-backend"})


@app.route("/api/applications/upload-url", methods=["POST"])
def generate_upload_url():
    body      = request.get_json() or {}
    filename  = body.get("filename", "application.pdf")
    app_id    = str(uuid4())
    s3_key    = f"uploads/{app_id}/{filename}"

    try:
        url = s3().generate_presigned_url(
            "put_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key, "ContentType": "application/pdf"},
            ExpiresIn=900,
        )
    except ClientError as e:
        return jsonify({"error": str(e)}), 500

    now = datetime.now(timezone.utc).isoformat()
    ddb_table().put_item(Item={
        "application_id": app_id,
        "status":         "uploading",
        "created_at":     now,
        "updated_at":     now,
        "s3_key":         s3_key,
        "filename":       filename,
    })

    return jsonify({"application_id": app_id, "upload_url": url, "s3_key": s3_key})


@app.route("/api/applications")
def list_applications():
    status_filter = request.args.get("status")
    try:
        if status_filter:
            resp = ddb_table().query(
                IndexName="status-created-index",
                KeyConditionExpression=Key("status").eq(status_filter),
                ScanIndexForward=False,
                Limit=100,
            )
        else:
            resp = ddb_table().scan(Limit=100)
    except ClientError as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"applications": resp.get("Items", [])})


@app.route("/api/applications/<app_id>")
def get_application(app_id):
    resp = ddb_table().get_item(Key={"application_id": app_id})
    item = resp.get("Item")
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@app.route("/api/applications/<app_id>/status", methods=["PATCH"])
def update_status(app_id):
    body       = request.get_json() or {}
    new_status = body.get("status")
    valid      = {"pending_review", "in_review", "approved", "rejected"}
    if new_status not in valid:
        return jsonify({"error": f"status must be one of {sorted(valid)}"}), 400

    now = datetime.now(timezone.utc).isoformat()
    try:
        ddb_table().update_item(
            Key={"application_id": app_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": new_status, ":u": now},
            ConditionExpression="attribute_exists(application_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return jsonify({"error": "not found"}), 404
        return jsonify({"error": str(e)}), 500

    return jsonify({"application_id": app_id, "status": new_status})


@app.route("/api/metrics")
def metrics():
    resp  = ddb_table().scan(Limit=500)
    items = resp.get("Items", [])
    by_status = {}
    for item in items:
        s = item.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    return jsonify({"total_applications": len(items), "by_status": by_status})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
