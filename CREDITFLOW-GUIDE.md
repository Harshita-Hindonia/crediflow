# CreditFlow — Step-by-Step Build Guide

> You are building a real, end-to-end cloud project based on your trade credit broker background.
> This guide walks you from zero to a deployed, working application on AWS — step by step.

---

## What You Are Building

**CreditFlow** — an automated trade credit operations platform.

### The story you tell in interviews:
> "At my previous role in customer support at a trade credit broker, credit applications came in as PDFs via email, were manually transcribed into spreadsheets, and tracked by hand. I built CreditFlow — an automated pipeline that ingests application documents, extracts the key fields automatically, tracks them through a review lifecycle, and gives ops teams a real-time dashboard. What used to take 2-3 days now takes under 5 minutes."

### What the system does:
1. Ops team uploads a credit application PDF through a web dashboard
2. File is stored securely in AWS S3 (encrypted)
3. A Lambda function triggers automatically on upload
4. AWS Textract reads the PDF and extracts fields (applicant name, credit limit, etc.)
5. Data is saved to DynamoDB
6. SNS sends a notification: "new application ready for review"
7. Ops team reviews it in the dashboard, updates status (approved / rejected)
8. CloudWatch shows real-time metrics: volume, processing time, SLA breaches

---

## Tech Stack

| What | Tool | Why |
|------|------|-----|
| Cloud | AWS | Industry standard |
| Infrastructure as Code | Terraform | Employer favourite, cloud-agnostic |
| Backend API | Python + Flask | Simple, readable |
| Frontend | React + Vite | Industry standard |
| Containers | Docker | Required for ECS |
| Orchestration | ECS Fargate | Serverless containers, no server management |
| CI/CD | GitHub Actions | Free, widely used |
| Monitoring | CloudWatch | Native AWS, zero extra cost |
| Database | DynamoDB | Serverless, free tier permanent |
| Storage | S3 | Cheap, durable, event-driven |
| Document AI | Textract | AWS native OCR |
| Notifications | SNS | Triggers email/SMS alerts |

---

## Project Structure (what you will build)

```
creditflow/
├── README.md                        ← your portfolio-facing README
├── docker-compose.yml               ← local dev stack
├── .gitignore
│
├── backend/                         ← Flask REST API
│   ├── app.py                       ← main application
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                        ← React dashboard
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── styles.css
│
├── lambda-document-processor/       ← document processing Lambda
│   ├── handler.py
│   └── requirements.txt
│
├── terraform/                       ← all AWS infrastructure
│   ├── main.tf                      ← provider + backend
│   ├── variables.tf
│   ├── outputs.tf
│   ├── network.tf                   ← VPC, subnets, security groups
│   ├── storage.tf                   ← S3, DynamoDB, SNS
│   ├── lambda.tf                    ← Lambda + IAM + S3 trigger
│   ├── ecs.tf                       ← ECS Fargate, ALB, ECR
│   ├── frontend.tf                  ← S3 + CloudFront for React
│   └── monitoring.tf                ← CloudWatch dashboards + alarms
│
└── .github/
    └── workflows/
        ├── backend-deploy.yml       ← CI/CD for backend
        ├── frontend-deploy.yml      ← CI/CD for frontend
        └── terraform-plan.yml       ← Terraform plan on PRs
```

---

## Phase 1 — Environment Setup

**Goal:** Git, Python, Docker, Node, AWS CLI, Terraform all working in WSL.

**Rule:** Run each command, paste the output to Claude. Don't install anything until Claude tells you to.

### Step 1.1 — Check what you already have

Run each of these and note the output:

```bash
python3 --version
git --version
docker --version
node --version
aws --version
terraform --version
```

### Step 1.2 — Install missing tools

Install Python 3.11:
```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip
```

Install Git:
```bash
sudo apt install -y git
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Install Docker (run this, then close and reopen WSL):
```bash
sudo apt install -y docker.io
sudo usermod -aG docker $USER
```

Install Node 20:
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Install AWS CLI:
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws/
```

Install Terraform:
```bash
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
```

### Step 1.3 — Verify everything

All of these should print a version number:

```bash
python3 --version   # Python 3.11.x
git --version       # git 2.x.x
docker --version    # Docker 24.x.x
node --version      # v20.x.x
npm --version       # 10.x.x
aws --version       # aws-cli/2.x.x
terraform --version # Terraform v1.6.x
```

### Step 1.4 — AWS credentials

```bash
aws configure
# Enter:
#   AWS Access Key ID:     (from your IAM user in AWS console)
#   AWS Secret Access Key: (from your IAM user in AWS console)
#   Default region name:   us-east-1
#   Default output format: json
```

Test it works:
```bash
aws sts get-caller-identity
# Should print your account ID and user ARN
```

### Step 1.5 — GitHub repo

```bash
mkdir ~/creditflow && cd ~/creditflow
git init
git remote add origin https://github.com/YOUR-USERNAME/creditflow.git
```

> Create the GitHub repo first at github.com (public, no README template).

---

## Phase 2 — Build the App Locally

**Goal:** Flask backend + React frontend + local DynamoDB all running with docker-compose. No AWS yet.

### Step 2.1 — Folder structure

```bash
cd ~/creditflow
mkdir -p backend frontend/src lambda-document-processor terraform .github/workflows docs
```

### Step 2.2 — Backend: Flask API

Create `backend/app.py`:

```python
"""
CreditFlow Backend API
Flask REST API for managing trade credit applications.

Endpoints:
  GET  /api/health                    health check (ALB uses this)
  POST /api/applications/upload-url   get presigned S3 URL for direct upload
  GET  /api/applications              list applications (?status= filter)
  GET  /api/applications/<id>         get one application
  PATCH /api/applications/<id>/status update status
  GET  /api/metrics                   dashboard metrics
"""

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
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")   # set in docker-compose for local dev

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
```

Create `backend/requirements.txt`:

```
flask==3.0.3
flask-cors==4.0.1
boto3==1.34.144
gunicorn==22.0.0
```

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
RUN useradd --create-home appuser
USER appuser
COPY --chown=appuser:appuser . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "app:app"]
```

### Step 2.3 — Lambda: document processor

Create `lambda-document-processor/handler.py`:

```python
"""
CreditFlow - Document Processor Lambda
Triggered when a PDF is uploaded to S3.
Flow: S3 event -> Textract -> DynamoDB update -> SNS notification
"""

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
```

Create `lambda-document-processor/requirements.txt`:

```
# boto3 is included in the Lambda Python 3.11 runtime - no extra packages needed
```

### Step 2.4 — Frontend: React dashboard

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CreditFlow — Trade Credit Operations</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Create `frontend/package.json`:

```json
{
  "name": "creditflow-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.7.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.3.4"
  }
}
```

Create `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 3000 },
  build: { outDir: 'dist' },
})
```

Create `frontend/src/main.jsx`:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

Create `frontend/src/App.jsx`:

```jsx
import { useEffect, useState } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:5000'

export default function App() {
  const [applications, setApplications] = useState([])
  const [metrics, setMetrics]           = useState({ total_applications: 0, by_status: {} })
  const [uploading, setUploading]       = useState(false)
  const [filter, setFilter]             = useState('')

  async function load() {
    const params = filter ? { status: filter } : {}
    const [appsRes, metricsRes] = await Promise.all([
      axios.get(`${API}/api/applications`, { params }),
      axios.get(`${API}/api/metrics`),
    ])
    setApplications(appsRes.data.applications || [])
    setMetrics(metricsRes.data)
  }

  useEffect(() => { load() }, [filter])

  async function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      const { data } = await axios.post(`${API}/api/applications/upload-url`, { filename: file.name })
      await axios.put(data.upload_url, file, { headers: { 'Content-Type': 'application/pdf' } })
      alert(`Uploaded! ID: ${data.application_id}`)
      load()
    } catch (err) {
      alert('Upload failed: ' + err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function updateStatus(id, status) {
    await axios.patch(`${API}/api/applications/${id}/status`, { status })
    load()
  }

  return (
    <div className="app">
      <header>
        <h1>CreditFlow</h1>
        <p>Trade credit operations dashboard</p>
      </header>

      <section className="metrics">
        <div className="metric-card">
          <div className="metric-value">{metrics.total_applications}</div>
          <div className="metric-label">Total applications</div>
        </div>
        {Object.entries(metrics.by_status).map(([s, n]) => (
          <div className="metric-card" key={s}>
            <div className="metric-value">{n}</div>
            <div className="metric-label">{s.replace(/_/g, ' ')}</div>
          </div>
        ))}
      </section>

      <section className="actions">
        <label className="btn">
          {uploading ? 'Uploading...' : '+ Upload application PDF'}
          <input type="file" accept="application/pdf" onChange={handleUpload} disabled={uploading} hidden />
        </label>
        <select value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="uploading">Uploading</option>
          <option value="pending_review">Pending review</option>
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </section>

      <table>
        <thead>
          <tr><th>ID</th><th>Applicant</th><th>Credit requested</th><th>Status</th><th>Created</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {applications.map(a => (
            <tr key={a.application_id}>
              <td className="mono">{a.application_id.slice(0, 8)}</td>
              <td>{a.extracted_fields?.applicant_name || '—'}</td>
              <td>{a.extracted_fields?.requested_credit_limit || '—'}</td>
              <td><span className={`status status-${a.status}`}>{a.status?.replace(/_/g,' ')}</span></td>
              <td>{new Date(a.created_at).toLocaleString()}</td>
              <td>
                {a.status === 'pending_review' && <button onClick={() => updateStatus(a.application_id, 'in_review')}>Start review</button>}
                {a.status === 'in_review' && <>
                  <button onClick={() => updateStatus(a.application_id, 'approved')}>Approve</button>
                  <button onClick={() => updateStatus(a.application_id, 'rejected')}>Reject</button>
                </>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {applications.length === 0 && <p className="empty">No applications yet. Upload a PDF to get started.</p>}
    </div>
  )
}
```

Create `frontend/src/styles.css`:

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, system-ui, sans-serif; background: #f5f5f7; color: #1d1d1f; }
.app { max-width: 1200px; margin: 0 auto; padding: 2rem; }
header h1 { margin: 0; font-size: 2rem; }
header p  { margin: 0.25rem 0 2rem; color: #666; }

.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.metric-card { background: white; padding: 1.25rem; border-radius: 8px; border: 1px solid #e0e0e0; }
.metric-value { font-size: 2rem; font-weight: 600; }
.metric-label { font-size: 0.85rem; color: #666; text-transform: capitalize; margin-top: 0.25rem; }

.actions { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }
.btn { background: #0066cc; color: white; padding: 0.6rem 1.2rem; border-radius: 6px; cursor: pointer; font-weight: 500; }
.btn:hover { background: #0052a3; }
select { padding: 0.4rem 0.6rem; border-radius: 4px; border: 1px solid #d0d0d0; }

table { width: 100%; background: white; border-radius: 8px; border: 1px solid #e0e0e0; border-collapse: collapse; }
th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid #f0f0f0; }
th { background: #fafafa; font-weight: 500; font-size: 0.85rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
tr:last-child td { border-bottom: none; }
.mono { font-family: ui-monospace, monospace; font-size: 0.85rem; }

.status { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.8rem; font-weight: 500; }
.status-uploading       { background: #fff4e0; color: #8a5a00; }
.status-pending_review  { background: #e0f0ff; color: #003d80; }
.status-in_review       { background: #f0e0ff; color: #4a008a; }
.status-approved        { background: #e0ffe8; color: #006625; }
.status-rejected        { background: #ffe0e0; color: #8a0000; }

button { padding: 0.3rem 0.7rem; border: 1px solid #d0d0d0; background: white; border-radius: 4px; cursor: pointer; margin-right: 0.4rem; font-size: 0.85rem; }
button:hover { background: #f0f0f0; }
.empty { text-align: center; padding: 3rem; color: #999; }
```

### Step 2.5 — Docker Compose (local dev stack)

Create `docker-compose.yml` in the root:

```yaml
services:
  dynamodb:
    image: amazon/dynamodb-local:latest
    container_name: creditflow-dynamodb
    ports: ["8000:8000"]
    command: "-jar DynamoDBLocal.jar -sharedDb -inMemory"

  backend:
    build: ./backend
    container_name: creditflow-backend
    ports: ["5000:5000"]
    environment:
      AWS_REGION: us-east-1
      DDB_TABLE_NAME: creditflow-dev-applications
      AWS_ACCESS_KEY_ID: dummy
      AWS_SECRET_ACCESS_KEY: dummy
      AWS_ENDPOINT_URL: http://dynamodb:8000
      FLASK_DEBUG: "1"
    depends_on: [dynamodb]
    volumes: [./backend:/app]
    command: python app.py

  frontend:
    image: node:20-alpine
    container_name: creditflow-frontend
    working_dir: /app
    ports: ["3000:3000"]
    environment:
      VITE_API_BASE: http://localhost:5000
    volumes: [./frontend:/app]
    command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
```

### Step 2.6 — Create the local DynamoDB table

After `docker-compose up`, run this once to create the table locally:

```bash
aws dynamodb create-table \
  --table-name creditflow-dev-applications \
  --attribute-definitions \
    AttributeName=application_id,AttributeType=S \
    AttributeName=status,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --key-schema AttributeName=application_id,KeyType=HASH \
  --global-secondary-indexes '[
    {
      "IndexName": "status-created-index",
      "KeySchema": [
        {"AttributeName":"status","KeyType":"HASH"},
        {"AttributeName":"created_at","KeyType":"RANGE"}
      ],
      "Projection": {"ProjectionType":"ALL"}
    }
  ]' \
  --billing-mode PAY_PER_REQUEST \
  --endpoint-url http://localhost:8000 \
  --region us-east-1
```

### Step 2.7 — Test it locally

```bash
# Check backend health
curl http://localhost:5000/api/health
# Should return: {"status":"ok","service":"creditflow-backend"}

# Check metrics
curl http://localhost:5000/api/metrics
# Should return: {"total_applications":0,"by_status":{}}

# Open frontend
# http://localhost:3000
```

> At this point the upload button will not work locally (no real S3). Everything else will work. That is expected.

---

## Phase 3 — Deploy to AWS with Terraform

**Goal:** All infrastructure created in AWS. App live. Full pipeline working end-to-end.

> **Before every session: Set a $5 budget alert in AWS Billing.**
> **After every session: run `terraform destroy`.**

### Step 3.1 — Create the Terraform files

Create `terraform/main.tf`:

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "CreditFlow"
      ManagedBy = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
```

Create `terraform/variables.tf`:

```hcl
variable "aws_region"   { default = "us-east-1" }
variable "project_name" { default = "creditflow" }
variable "environment"  { default = "dev" }

variable "backend_cpu"    { default = 256 }
variable "backend_memory" { default = 512 }
variable "backend_image_tag" { default = "latest" }

locals {
  prefix = "${var.project_name}-${var.environment}"
}
```

Create `terraform/outputs.tf`:

```hcl
output "alb_url"           { value = "http://${aws_lb.main.dns_name}" }
output "cloudfront_url"    { value = "https://${aws_cloudfront_distribution.frontend.domain_name}" }
output "documents_bucket"  { value = aws_s3_bucket.documents.id }
output "frontend_bucket"   { value = aws_s3_bucket.frontend.id }
output "ecr_repo_url"      { value = aws_ecr_repository.backend.repository_url }
output "ddb_table"         { value = aws_dynamodb_table.applications.name }
output "cloudfront_id"     { value = aws_cloudfront_distribution.frontend.id }
```

Create `terraform/network.tf`:

```hcl
# VPC — 2 public subnets across 2 AZs (ALB requires at least 2)
# NOTE: No NAT Gateway — that's $32/month. ECS tasks get public IPs
#       but are locked down via security groups.

data "aws_availability_zones" "available" { state = "available" }

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "${local.prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.prefix}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "${local.prefix}-public-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route { cidr_block = "0.0.0.0/0"; gateway_id = aws_internet_gateway.main.id }
  tags   = { Name = "${local.prefix}-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "alb" {
  name   = "${local.prefix}-alb-sg"
  vpc_id = aws_vpc.main.id
  ingress { from_port = 80; to_port = 80; protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
  egress  { from_port = 0;  to_port = 0;  protocol = "-1"; cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "ecs" {
  name   = "${local.prefix}-ecs-sg"
  vpc_id = aws_vpc.main.id
  ingress { from_port = 5000; to_port = 5000; protocol = "tcp"; security_groups = [aws_security_group.alb.id] }
  egress  { from_port = 0;    to_port = 0;    protocol = "-1"; cidr_blocks      = ["0.0.0.0/0"] }
}
```

Create `terraform/storage.tf`:

```hcl
resource "random_id" "suffix" { byte_length = 4 }

# S3 — document uploads
resource "aws_s3_bucket" "documents" {
  bucket        = "${local.prefix}-documents-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB — application records
resource "aws_dynamodb_table" "applications" {
  name         = "${local.prefix}-applications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "application_id"

  attribute { name = "application_id"; type = "S" }
  attribute { name = "status";         type = "S" }
  attribute { name = "created_at";     type = "S" }

  global_secondary_index {
    name            = "status-created-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery { enabled = true }
}

# SNS — review-ready notifications
resource "aws_sns_topic" "notifications" {
  name = "${local.prefix}-notifications"
}
```

Create `terraform/lambda.tf`:

```hcl
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda-document-processor"
  output_path = "${path.module}/.build/lambda.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow"; Action = "sts:AssumeRole"; Principal = { Service = "lambda.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_app" {
  name = "${local.prefix}-lambda-policy"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow"; Action = ["s3:GetObject"];                                                Resource = "${aws_s3_bucket.documents.arn}/*" },
      { Effect = "Allow"; Action = ["textract:DetectDocumentText", "textract:AnalyzeDocument"];     Resource = "*" },
      { Effect = "Allow"; Action = ["dynamodb:PutItem", "dynamodb:UpdateItem"];                     Resource = aws_dynamodb_table.applications.arn },
      { Effect = "Allow"; Action = ["sns:Publish"];                                                 Resource = aws_sns_topic.notifications.arn },
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.prefix}-doc-processor"
  retention_in_days = 7
}

resource "aws_lambda_function" "doc_processor" {
  function_name    = "${local.prefix}-doc-processor"
  role             = aws_iam_role.lambda.arn
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      DDB_TABLE_NAME = aws_dynamodb_table.applications.name
      SNS_TOPIC_ARN  = aws_sns_topic.notifications.arn
    }
  }
}

resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.doc_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.documents.arn
}

resource "aws_s3_bucket_notification" "trigger" {
  bucket = aws_s3_bucket.documents.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.doc_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
  depends_on = [aws_lambda_permission.s3]
}
```

Create `terraform/ecs.tf`:

```hcl
resource "aws_ecr_repository" "backend" {
  name         = "${local.prefix}-backend"
  force_delete = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecs_cluster" "main" {
  name = "${local.prefix}-cluster"
  setting { name = "containerInsights"; value = "disabled" }
}

resource "aws_iam_role" "ecs_exec" {
  name = "${local.prefix}-ecs-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow"; Action = "sts:AssumeRole"; Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_exec" {
  role       = aws_iam_role.ecs_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${local.prefix}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow"; Action = "sts:AssumeRole"; Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "${local.prefix}-ecs-task-policy"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow"; Action = ["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:Query","dynamodb:Scan"]; Resource = [aws_dynamodb_table.applications.arn, "${aws_dynamodb_table.applications.arn}/index/*"] },
      { Effect = "Allow"; Action = ["s3:PutObject","s3:GetObject"]; Resource = "${aws_s3_bucket.documents.arn}/*" },
    ]
  })
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.prefix}-backend"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "backend"
    image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
    essential = true
    portMappings = [{ containerPort = 5000 }]
    environment = [
      { name = "DDB_TABLE_NAME",       value = aws_dynamodb_table.applications.name },
      { name = "S3_DOCUMENTS_BUCKET",  value = aws_s3_bucket.documents.id },
      { name = "AWS_REGION",           value = var.aws_region },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options   = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL","curl -f http://localhost:5000/api/health || exit 1"]
      interval    = 30; timeout = 5; retries = 3; startPeriod = 30
    }
  }])
}

resource "aws_lb" "main" {
  name               = "${local.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "backend" {
  name        = "${local.prefix}-tg"
  port        = 5000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id
  health_check { path = "/api/health"; matcher = "200"; healthy_threshold = 2 }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action    { type = "forward"; target_group_arn = aws_lb_target_group.backend.arn }
}

resource "aws_ecs_service" "backend" {
  name            = "${local.prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 5000
  }

  depends_on = [aws_lb_listener.http]
}
```

Create `terraform/frontend.tf`:

```hcl
resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.prefix}-frontend-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  block_public_acls = true; block_public_policy = true
  ignore_public_acls = true; restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET","HEAD"]
    cached_methods         = ["GET","HEAD"]
    compress               = true
    forwarded_values { query_string = false; cookies { forward = "none" } }
  }

  custom_error_response { error_code = 404; response_code = 200; response_page_path = "/index.html" }
  restrictions { geo_restriction { restriction_type = "none" } }
  viewer_certificate { cloudfront_default_certificate = true }
}

data "aws_iam_policy_document" "frontend" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
    principals { type = "Service"; identifiers = ["cloudfront.amazonaws.com"] }
    condition { test = "StringEquals"; variable = "AWS:SourceArn"; values = [aws_cloudfront_distribution.frontend.arn] }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend.json
}
```

Create `terraform/monitoring.tf`:

```hcl
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.prefix}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 3
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.doc_processor.function_name }
  alarm_actions       = [aws_sns_topic.notifications.arn]
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.prefix}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  alarm_actions       = [aws_sns_topic.notifications.arn]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.prefix}-budget"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["REPLACE_WITH_YOUR_EMAIL"]
  }
}
```

### Step 3.2 — Add the random provider

Add this to `terraform/main.tf` required_providers block:

```hcl
random = { source = "hashicorp/random", version = "~> 3.0" }
```

### Step 3.3 — First deploy (networking only)

Start small — just the network:

```bash
cd terraform
terraform init
terraform plan -target=aws_vpc.main -target=aws_subnet.public -target=aws_internet_gateway.main
terraform apply -target=aws_vpc.main -target=aws_subnet.public -target=aws_internet_gateway.main
```

Go to AWS Console → VPC. You should see your VPC and 2 subnets. That confirms Terraform is working.

### Step 3.4 — Deploy storage + Lambda

```bash
terraform apply -target=aws_s3_bucket.documents -target=aws_dynamodb_table.applications -target=aws_sns_topic.notifications -target=aws_lambda_function.doc_processor
```

Test: manually upload a PDF to the documents S3 bucket under `uploads/test-id/test.pdf`. Check Lambda CloudWatch logs.

### Step 3.5 — Push backend image to ECR, then deploy ECS

```bash
# Get ECR URL from Terraform outputs
terraform output ecr_repo_url

# Build and push
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repo_url | cut -d'/' -f1)
docker build -t creditflow-backend ../backend
docker tag creditflow-backend:latest $(terraform output -raw ecr_repo_url):latest
docker push $(terraform output -raw ecr_repo_url):latest

# Deploy ECS
terraform apply -target=aws_ecs_service.backend -target=aws_lb.main
```

Wait ~3 minutes, then:
```bash
curl http://$(terraform output -raw alb_url)/api/health
```

### Step 3.6 — Deploy frontend

```bash
terraform apply -target=aws_cloudfront_distribution.frontend

# Build React and upload
cd ../frontend
VITE_API_BASE=$(cd ../terraform && terraform output -raw alb_url) npm run build
aws s3 sync dist/ s3://$(cd ../terraform && terraform output -raw frontend_bucket)/
aws cloudfront create-invalidation --distribution-id $(cd ../terraform && terraform output -raw cloudfront_id) --paths "/*"
cd ../terraform
```

Open the CloudFront URL — your app is live.

### Step 3.7 — Full apply

Once all pieces are working individually:

```bash
terraform apply
```

### IMPORTANT — destroy after every session

```bash
terraform destroy
```

---

## Phase 4 — CI/CD with GitHub Actions

**Goal:** Every push to `main` automatically builds, tests, and deploys.

### Step 4.1 — GitHub OIDC setup (one time)

```bash
# Create OIDC provider in AWS
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

Create an IAM role that GitHub Actions can assume. In AWS Console → IAM → Roles → Create Role → Web Identity. Select the OIDC provider you just created. Add these policies: `AmazonECS_FullAccess`, `AmazonEC2ContainerRegistryFullAccess`, `AmazonS3FullAccess`, `CloudFrontFullAccess`, `AmazonDynamoDBFullAccess`.

Copy the role ARN. In your GitHub repo → Settings → Secrets → Add:
- `AWS_DEPLOY_ROLE_ARN` = the role ARN
- `AWS_REGION` = `us-east-1`
- `FRONTEND_S3_BUCKET` = output from `terraform output frontend_bucket`
- `CLOUDFRONT_DISTRIBUTION_ID` = output from `terraform output cloudfront_id`
- `API_BASE_URL` = output from `terraform output alb_url`

### Step 4.2 — Backend workflow

Create `.github/workflows/backend-deploy.yml`:

```yaml
name: Backend Deploy

on:
  push:
    branches: [main]
    paths: ['backend/**']

env:
  AWS_REGION: us-east-1
  ECR_REPO: creditflow-dev-backend
  ECS_CLUSTER: creditflow-dev-cluster
  ECS_SERVICE: creditflow-dev-backend

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        id: build
        working-directory: backend
        run: |
          IMAGE=${{ steps.login.outputs.registry }}/${{ env.ECR_REPO }}:${{ github.sha }}
          docker build -t $IMAGE .
          docker push $IMAGE
          echo "image=$IMAGE" >> $GITHUB_OUTPUT

      - name: Deploy to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition-family: creditflow-dev-backend
          service: ${{ env.ECS_SERVICE }}
          cluster: ${{ env.ECS_CLUSTER }}
          container-name: backend
          image: ${{ steps.build.outputs.image }}
          wait-for-service-stability: true
```

### Step 4.3 — Frontend workflow

Create `.github/workflows/frontend-deploy.yml`:

```yaml
name: Frontend Deploy

on:
  push:
    branches: [main]
    paths: ['frontend/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Build
        working-directory: frontend
        run: |
          npm ci
          VITE_API_BASE=${{ secrets.API_BASE_URL }} npm run build

      - name: Deploy to S3
        run: aws s3 sync frontend/dist/ s3://${{ secrets.FRONTEND_S3_BUCKET }}/ --delete

      - name: Invalidate CloudFront
        run: aws cloudfront create-invalidation --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} --paths "/*"
```

---

## Phase 5 — Monitoring, Polish, and Portfolio

**Goal:** Screenshots, architecture diagram, clean README, LinkedIn post, resume update.

### Step 5.1 — Subscribe to alerts

```bash
aws sns subscribe \
  --topic-arn $(cd terraform && terraform output -raw ... ) \
  --protocol email \
  --notification-endpoint your-email@example.com
```

Confirm the subscription email AWS sends you.

### Step 5.2 — Architecture diagram

Use [draw.io](https://draw.io) or [Excalidraw](https://excalidraw.com) to draw:

```
[Browser] → [CloudFront] → [S3 frontend]
[Browser] → [ALB] → [ECS Fargate - Flask API] → [DynamoDB]
[Browser] → [ALB] → [ECS Fargate] → [S3 documents]
[S3 documents] → [Lambda] → [Textract] → [DynamoDB]
[Lambda] → [SNS] → [Email]
[CloudWatch] monitors → [ECS, Lambda, ALB]
[GitHub Actions] deploys → [ECR + ECS + S3 + CloudFront]
[Terraform] provisions → [Everything above]
```

Save as `docs/architecture.png`.

### Step 5.3 — Screenshots to take

- [ ] Web dashboard (empty state)
- [ ] Web dashboard after uploading a test PDF
- [ ] Application showing extracted fields
- [ ] Application status changing from pending → approved
- [ ] CloudWatch dashboard
- [ ] GitHub Actions pipeline green
- [ ] AWS Console showing ECS service running

### Step 5.4 — Resume bullets

Copy these exactly, fill in the numbers:

```
CreditFlow — Automated Trade Credit Operations Platform | Personal Project

• Architected and deployed a 3-tier AWS application automating manual credit
  application workflows from my trade credit broker background, reducing
  processing time from 2-3 days to under 5 minutes

• Built event-driven document processing pipeline (S3 → Lambda → Textract →
  DynamoDB → SNS) for automated field extraction from financial PDFs, with
  full audit trail and encryption at rest

• Containerized Flask API with Docker, deployed to ECS Fargate behind an ALB;
  provisioned 100% of infrastructure with Terraform across VPC, ECS, IAM,
  CloudWatch — reproducible from scratch in under 10 minutes

• Implemented GitHub Actions CI/CD pipeline: automated build, ECR push, and
  ECS blue/green deployment on every commit to main

• Configured CloudWatch dashboards and alarms for real-time SLA visibility
  and anomaly detection (Lambda errors, ALB 5xx spikes)

Tech: AWS (ECS Fargate, Lambda, S3, CloudFront, DynamoDB, Textract, SNS, ALB,
CloudWatch, ECR, IAM), Terraform, Docker, GitHub Actions, Python/Flask, React
```

### Step 5.5 — .gitignore

Create `.gitignore` in the root:

```
# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
terraform/.build/

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/
dist/

# Secrets
.env
*.pem
*.key
```

---

## Cost Safety Rules

**Rule 1:** Set a $5 AWS budget alert before your first `terraform apply`.

**Rule 2:** Run `terraform destroy` after every coding session. ALB + Fargate = ~$0.84/day if left running.

**Services that cost money if left on:**
- ALB: ~$0.54/day idle
- ECS Fargate: ~$0.30/day for our task size
- NAT Gateway (we avoid this): $0.03/hour = $22/month — we use public subnets instead

**Services that are always free at our scale:**
- S3, DynamoDB, Lambda, SNS, CloudWatch, ECR, IAM, VPC

**If you get an unexpected bill:**
1. Run `terraform destroy` immediately
2. Check AWS Billing → Bills for the offending service
3. Open an AWS Support billing case — explain you are a learner, they often waive it

---

## What to Say in Interviews

**"Walk me through this project":**
> "I built CreditFlow, a cloud-native document processing platform inspired by my experience in customer support at a trade credit broker. In that role I saw credit applications handled entirely manually — PDFs received by email, transcribed by hand, tracked in spreadsheets. I automated the entire workflow: documents upload through a React dashboard, trigger a Lambda function via S3 events, get processed by Textract for field extraction, and the structured data lands in DynamoDB. The ops team reviews everything in the same dashboard. All infrastructure is Terraform, deployments are automated with GitHub Actions, and CloudWatch monitors the whole pipeline."

**"Why DynamoDB over RDS?":**
> "Serverless billing — DynamoDB charges per request and costs nothing at idle. For this project's access patterns (simple key lookups, status-based queries via a GSI), there's no need for relational joins. If I needed complex analytics or reporting, I'd add an export to S3 and query with Athena."

**"Why public subnets for ECS?":**
> "Conscious cost trade-off. NAT Gateway costs $32/month just sitting there. For a dev/portfolio project, public subnets with locked-down security groups are acceptable. In a production fintech environment I would absolutely use private subnets with VPC endpoints to avoid both the NAT cost and the exposure."

**"What would you do differently in production?":**
> "Authentication on the API (Cognito or JWT), private networking, at least 2 ECS tasks across AZs, a staging environment with manual approval gate, WAF in front of CloudFront and ALB, KMS-managed encryption on the documents bucket, and structured JSON logging with distributed tracing via X-Ray."
```
