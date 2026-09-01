# Google Cloud Platform Deployment Guide

This guide provides step-by-step instructions for deploying the Automated Credit Scoring application to Google Cloud Platform.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Manual Deployment Steps](#manual-deployment-steps)
4. [Configuration](#configuration)
5. [Post-Deployment](#post-deployment)
6. [Troubleshooting](#troubleshooting)

## Prerequisites

1. **Google Cloud Account**
   - Create a GCP account at https://cloud.google.com
   - Enable billing (required for Cloud SQL and Cloud Run)

2. **Install Google Cloud SDK**
   ```bash
   # Linux/Mac
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL
   gcloud init
   
   # Or download from: https://cloud.google.com/sdk/docs/install
   ```

3. **Set up Authentication**
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

## Quick Start

Use the automated deployment script:

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
- Enable required APIs
- Create Cloud SQL instance
- Create Cloud Storage buckets
- Build and deploy both backend and frontend
- Configure basic settings

## Manual Deployment Steps

### Step 1: Enable Required APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage-component.googleapis.com \
  secretmanager.googleapis.com
```

### Step 2: Create Cloud SQL PostgreSQL Instance

```bash
# Create instance
gcloud sql instances create credit-scoring-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password=YOUR_SECURE_PASSWORD

# Create database
gcloud sql databases create credit_scoring --instance=credit-scoring-db

# Create user
gcloud sql users create app_user \
  --instance=credit-scoring-db \
  --password=YOUR_APP_USER_PASSWORD
```

**Get connection name:**
```bash
gcloud sql instances describe credit-scoring-db --format="value(connectionName)"
# Output: PROJECT_ID:REGION:credit-scoring-db
```

### Step 3: Initialize Database Schema

**Option A: Using Cloud SQL Proxy (Recommended)**
```bash
# Download Cloud SQL Proxy
curl -o cloud_sql_proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64
chmod +x cloud_sql_proxy

# Start proxy
./cloud_sql_proxy -instances=PROJECT_ID:REGION:credit-scoring-db=tcp:5432

# In another terminal, set environment variables
export DATABASE_URL="postgresql://app_user:PASSWORD@localhost:5432/credit_scoring"
export PG_DBNAME=credit_scoring
export PG_USER=app_user
export PG_PASSWORD=YOUR_APP_USER_PASSWORD
export PG_HOST=localhost
export PG_PORT=5432

# Run schema initialization
cd backend
python validate_and_migrate_schema.py
```

**Option B: Using Authorized IP**
```bash
# Add your IP to authorized networks
gcloud sql instances patch credit-scoring-db \
  --authorized-networks=YOUR_IP_ADDRESS/32

# Connect directly
psql -h INSTANCE_IP -U app_user -d credit_scoring
```

### Step 4: Create Cloud Storage Buckets

```bash
PROJECT_ID=$(gcloud config get-value project)

# Create buckets
gsutil mb -p $PROJECT_ID -l us-central1 gs://$PROJECT_ID-uploads
gsutil mb -p $PROJECT_ID -l us-central1 gs://$PROJECT_ID-artifacts

# Set permissions (if needed)
gsutil iam ch allUsers:objectViewer gs://$PROJECT_ID-uploads
```

### Step 5: Store Secrets in Secret Manager

```bash
# JWT Secret
echo -n "your-super-secret-jwt-key" | gcloud secrets create jwt-secret --data-file=-

# HuggingFace Token (optional)
echo -n "your-hf-token" | gcloud secrets create hf-token --data-file=-
```

### Step 6: Build and Deploy Backend

```bash
# Build Docker image
gcloud builds submit --tag gcr.io/$PROJECT_ID/credit-scoring-backend

# Deploy to Cloud Run
gcloud run deploy credit-scoring-backend \
  --image gcr.io/$PROJECT_ID/credit-scoring-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --add-cloudsql-instances=PROJECT_ID:REGION:credit-scoring-db \
  --set-env-vars="DATABASE_URL=postgresql://app_user:PASSWORD@/credit_scoring?host=/cloudsql/PROJECT_ID:REGION:credit-scoring-db" \
  --set-env-vars="GCS_UPLOADS_BUCKET=$PROJECT_ID-uploads" \
  --set-env-vars="GCS_ARTIFACTS_BUCKET=$PROJECT_ID-artifacts" \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="PORT=8080" \
  --update-secrets=JWT_SECRET=jwt-secret:latest,HF_TOKEN=hf-token:latest \
  --memory=2Gi \
  --cpu=2 \
  --timeout=3600 \
  --max-instances=10
```

**Get backend URL:**
```bash
BACKEND_URL=$(gcloud run services describe credit-scoring-backend \
  --region us-central1 \
  --format="value(status.url)")
echo $BACKEND_URL
```

### Step 7: Build and Deploy Frontend

**Update frontend config:**
```bash
# Edit src/config.ts and update API_BASE_URL with backend URL
```

**Build and deploy:**
```bash
# Build Docker image
gcloud builds submit --tag gcr.io/$PROJECT_ID/credit-scoring-frontend

# Deploy to Cloud Run
gcloud run deploy credit-scoring-frontend \
  --image gcr.io/$PROJECT_ID/credit-scoring-frontend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --timeout=300 \
  --max-instances=10
```

**Get frontend URL:**
```bash
FRONTEND_URL=$(gcloud run services describe credit-scoring-frontend \
  --region us-central1 \
  --format="value(status.url)")
echo $FRONTEND_URL
```

### Step 8: Update Backend CORS

```bash
# Update ALLOWED_ORIGINS environment variable
gcloud run services update credit-scoring-backend \
  --update-env-vars="ALLOWED_ORIGINS=$FRONTEND_URL" \
  --region us-central1
```

## Configuration

### Environment Variables

**Backend (Cloud Run):**
- `DATABASE_URL`: PostgreSQL connection string
- `GCS_UPLOADS_BUCKET`: Cloud Storage bucket for uploads
- `GCS_ARTIFACTS_BUCKET`: Cloud Storage bucket for artifacts
- `JWT_SECRET`: Secret for JWT token signing
- `HF_TOKEN`: HuggingFace API token (optional)
- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins
- `ENVIRONMENT`: Set to `production`
- `PORT`: Set to `8080`

**Frontend:**
- `VITE_API_BASE_URL`: Backend API URL (set during build)

### Database Connection String Format

For Cloud SQL with Unix socket:
```
postgresql://USER:PASSWORD@/DATABASE_NAME?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME
```

For Cloud SQL with TCP:
```
postgresql://USER:PASSWORD@INSTANCE_IP:5432/DATABASE_NAME
```

## Post-Deployment

### 1. Verify Deployment

```bash
# Check backend health
curl https://YOUR-BACKEND-URL.run.app/health

# Check frontend
curl https://YOUR-FRONTEND-URL.run.app/health
```

### 2. Test Database Connection

```bash
# Test from Cloud Run service
gcloud run services proxy credit-scoring-backend --region us-central1
# Then visit: http://localhost:8080/api/db-health
```

### 3. Monitor Logs

```bash
# Backend logs
gcloud run services logs read credit-scoring-backend --region us-central1

# Frontend logs
gcloud run services logs read credit-scoring-frontend --region us-central1
```

### 4. Set Up Custom Domain (Optional)

```bash
# Map custom domain to Cloud Run service
gcloud run domain-mappings create \
  --service credit-scoring-frontend \
  --domain your-domain.com \
  --region us-central1
```

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Verify Cloud SQL instance is running
   - Check connection name format
   - Ensure Cloud Run service has Cloud SQL connection
   - Verify database credentials

2. **File Upload Fails**
   - Check Cloud Storage bucket permissions
   - Verify `GCS_UPLOADS_BUCKET` environment variable
   - Check service account has Storage Admin role

3. **CORS Errors**
   - Verify `ALLOWED_ORIGINS` includes frontend URL
   - Check frontend `API_BASE_URL` is correct
   - Ensure no trailing slashes in URLs

4. **Build Fails**
   - Check Dockerfile syntax
   - Verify all dependencies in requirements.txt
   - Check Cloud Build logs for errors

5. **Service Won't Start**
   - Check Cloud Run logs
   - Verify environment variables are set
   - Check health endpoint is accessible

### Useful Commands

```bash
# View service details
gcloud run services describe credit-scoring-backend --region us-central1

# Update environment variables
gcloud run services update credit-scoring-backend \
  --update-env-vars="KEY=VALUE" \
  --region us-central1

# View recent logs
gcloud run services logs read credit-scoring-backend \
  --region us-central1 \
  --limit 50

# Delete service (if needed)
gcloud run services delete credit-scoring-backend --region us-central1
```

## Cost Optimization

1. **Cloud SQL**
   - Use `db-f1-micro` for development
   - Enable automatic backups only if needed
   - Consider using Cloud SQL Proxy for local development

2. **Cloud Run**
   - Set `min-instances=0` to scale to zero
   - Adjust memory/CPU based on actual usage
   - Use request timeout appropriately

3. **Cloud Storage**
   - Set lifecycle policies for old files
   - Use appropriate storage classes
   - Enable object versioning only if needed

## Security Best Practices

1. **Secrets Management**
   - Use Secret Manager for sensitive data
   - Rotate secrets regularly
   - Never commit secrets to git

2. **Database Security**
   - Use Cloud SQL private IP when possible
   - Restrict authorized networks
   - Use strong passwords

3. **Cloud Storage**
   - Set appropriate IAM permissions
   - Enable bucket versioning for critical data
   - Use signed URLs for temporary access

4. **Cloud Run**
   - Use IAM for authentication when possible
   - Enable VPC connector for private resources
   - Set appropriate resource limits

## Support

For issues or questions:
1. Check Cloud Run logs
2. Review Cloud Build logs
3. Check database connection status
4. Verify environment variables

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Cloud Build Documentation](https://cloud.google.com/build/docs)

