# Quick Deployment Guide

## Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated
- Project ID set: `gcloud config set project YOUR_PROJECT_ID`

## One-Command Deployment

```bash
./deploy.sh
```

Follow the prompts to:
1. Create Cloud SQL instance
2. Create Cloud Storage buckets
3. Store secrets
4. Build and deploy

## Manual Quick Deploy

### 1. Set Variables
```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1
```

### 2. Enable APIs
```bash
gcloud services enable cloudbuild.googleapis.com run.googleapis.com sqladmin.googleapis.com storage-component.googleapis.com
```

### 3. Create Cloud SQL
```bash
gcloud sql instances create credit-scoring-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --root-password=CHANGE_ME

gcloud sql databases create credit_scoring --instance=credit-scoring-db
gcloud sql users create app_user --instance=credit-scoring-db --password=CHANGE_ME
```

### 4. Create Buckets
```bash
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-uploads
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-artifacts
```

### 5. Get Connection Name
```bash
CONNECTION_NAME=$(gcloud sql instances describe credit-scoring-db --format="value(connectionName)")
echo $CONNECTION_NAME
```

### 6. Update cloudbuild.yaml
Edit `cloudbuild.yaml` and set:
```yaml
_CLOUD_SQL_INSTANCE: 'YOUR_CONNECTION_NAME'
```

### 7. Deploy
```bash
gcloud builds submit --config=cloudbuild.yaml
```

### 8. Set Environment Variables
After deployment, update backend service:
```bash
gcloud run services update credit-scoring-backend \
  --update-env-vars="DATABASE_URL=postgresql://app_user:PASSWORD@/credit_scoring?host=/cloudsql/$CONNECTION_NAME" \
  --update-env-vars="GCS_UPLOADS_BUCKET=$PROJECT_ID-uploads" \
  --update-env-vars="GCS_ARTIFACTS_BUCKET=$PROJECT_ID-artifacts" \
  --region=$REGION
```

### 9. Get URLs
```bash
BACKEND_URL=$(gcloud run services describe credit-scoring-backend --region=$REGION --format="value(status.url)")
FRONTEND_URL=$(gcloud run services describe credit-scoring-frontend --region=$REGION --format="value(status.url)")

echo "Backend: $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
```

### 10. Update CORS
```bash
gcloud run services update credit-scoring-backend \
  --update-env-vars="ALLOWED_ORIGINS=$FRONTEND_URL" \
  --region=$REGION
```

### 11. Initialize Database
Use Cloud SQL Proxy to connect and run:
```bash
cd backend
python validate_and_migrate_schema.py
```

## Verify Deployment

```bash
# Check backend
curl https://YOUR-BACKEND-URL/health

# Check frontend
curl https://YOUR-FRONTEND-URL/health
```

## Next Steps

1. Update `src/config.ts` with backend URL
2. Rebuild and redeploy frontend
3. Test all functionality
4. Set up monitoring and alerts

For detailed instructions, see `GCP_DEPLOYMENT.md`.

