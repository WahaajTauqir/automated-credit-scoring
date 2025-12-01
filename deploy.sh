#!/bin/bash
# Deployment script for Google Cloud Platform

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Automated Credit Scoring - GCP Deployment ===${NC}\n"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed.${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}No project set. Please set your GCP project:${NC}"
    read -p "Project ID: " PROJECT_ID
    gcloud config set project $PROJECT_ID
fi

echo -e "${GREEN}Using project: ${PROJECT_ID}${NC}\n"

# Set region
REGION=${REGION:-us-central1}
echo -e "${GREEN}Using region: ${REGION}${NC}\n"

# Step 1: Enable required APIs
echo -e "${YELLOW}Step 1: Enabling required APIs...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    storage-component.googleapis.com \
    secretmanager.googleapis.com \
    --project=$PROJECT_ID

echo -e "${GREEN}✓ APIs enabled${NC}\n"

# Step 2: Create Cloud SQL instance (if it doesn't exist)
echo -e "${YELLOW}Step 2: Setting up Cloud SQL...${NC}"
INSTANCE_NAME="credit-scoring-db"

if ! gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID &>/dev/null; then
    echo "Creating Cloud SQL instance..."
    read -sp "Enter root password for database: " DB_ROOT_PASSWORD
    echo
    
    gcloud sql instances create $INSTANCE_NAME \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --root-password=$DB_ROOT_PASSWORD \
        --project=$PROJECT_ID
    
    # Create database
    gcloud sql databases create credit_scoring --instance=$INSTANCE_NAME --project=$PROJECT_ID
    
    # Create user
    read -sp "Enter password for app_user: " APP_USER_PASSWORD
    echo
    gcloud sql users create app_user \
        --instance=$INSTANCE_NAME \
        --password=$APP_USER_PASSWORD \
        --project=$PROJECT_ID
    
    echo -e "${GREEN}✓ Cloud SQL instance created${NC}"
else
    echo -e "${GREEN}✓ Cloud SQL instance already exists${NC}"
fi

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --format="value(connectionName)" --project=$PROJECT_ID)
echo -e "${GREEN}Connection name: ${CONNECTION_NAME}${NC}\n"

# Step 3: Create Cloud Storage buckets
echo -e "${YELLOW}Step 3: Creating Cloud Storage buckets...${NC}"
UPLOADS_BUCKET="${PROJECT_ID}-uploads"
ARTIFACTS_BUCKET="${PROJECT_ID}-artifacts"

if ! gsutil ls -b gs://$UPLOADS_BUCKET &>/dev/null; then
    gsutil mb -p $PROJECT_ID -l $REGION gs://$UPLOADS_BUCKET
    echo -e "${GREEN}✓ Created uploads bucket${NC}"
else
    echo -e "${GREEN}✓ Uploads bucket already exists${NC}"
fi

if ! gsutil ls -b gs://$ARTIFACTS_BUCKET &>/dev/null; then
    gsutil mb -p $PROJECT_ID -l $REGION gs://$ARTIFACTS_BUCKET
    echo -e "${GREEN}✓ Created artifacts bucket${NC}"
else
    echo -e "${GREEN}✓ Artifacts bucket already exists${NC}"
fi

echo ""

# Step 4: Store secrets (optional)
echo -e "${YELLOW}Step 4: Setting up secrets (optional)...${NC}"
read -p "Do you want to store secrets in Secret Manager? (y/n): " STORE_SECRETS

if [ "$STORE_SECRETS" = "y" ]; then
    read -sp "Enter JWT_SECRET: " JWT_SECRET
    echo
    echo -n "$JWT_SECRET" | gcloud secrets create jwt-secret --data-file=- --project=$PROJECT_ID 2>/dev/null || \
        echo -n "$JWT_SECRET" | gcloud secrets versions add jwt-secret --data-file=- --project=$PROJECT_ID
    
    read -sp "Enter HF_TOKEN (optional, press Enter to skip): " HF_TOKEN
    echo
    if [ -n "$HF_TOKEN" ]; then
        echo -n "$HF_TOKEN" | gcloud secrets create hf-token --data-file=- --project=$PROJECT_ID 2>/dev/null || \
            echo -n "$HF_TOKEN" | gcloud secrets versions add hf-token --data-file=- --project=$PROJECT_ID
    fi
    
    echo -e "${GREEN}✓ Secrets stored${NC}"
fi

echo ""

# Step 5: Build and deploy
echo -e "${YELLOW}Step 5: Building and deploying...${NC}"
read -p "Do you want to build and deploy now? (y/n): " DEPLOY_NOW

if [ "$DEPLOY_NOW" = "y" ]; then
    # Update cloudbuild.yaml with connection name
    sed -i.bak "s|_CLOUD_SQL_INSTANCE: ''|_CLOUD_SQL_INSTANCE: '${CONNECTION_NAME}'|" cloudbuild.yaml
    
    # Submit build
    gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID
    
    # Restore original cloudbuild.yaml
    mv cloudbuild.yaml.bak cloudbuild.yaml
    
    echo -e "${GREEN}✓ Deployment complete!${NC}\n"
    
    # Get service URLs
    BACKEND_URL=$(gcloud run services describe credit-scoring-backend --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)
    FRONTEND_URL=$(gcloud run services describe credit-scoring-frontend --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)
    
    echo -e "${GREEN}Backend URL: ${BACKEND_URL}${NC}"
    echo -e "${GREEN}Frontend URL: ${FRONTEND_URL}${NC}\n"
    
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Update frontend/src/config.ts with backend URL: ${BACKEND_URL}"
    echo "2. Set environment variables in Cloud Run:"
    echo "   - DATABASE_URL"
    echo "   - GCS_UPLOADS_BUCKET=${UPLOADS_BUCKET}"
    echo "   - GCS_ARTIFACTS_BUCKET=${ARTIFACTS_BUCKET}"
    echo "   - ALLOWED_ORIGINS=${FRONTEND_URL}"
    echo "3. Configure secrets in Cloud Run if you stored them"
else
    echo -e "${YELLOW}To deploy later, run:${NC}"
    echo "gcloud builds submit --config=cloudbuild.yaml"
fi

echo -e "\n${GREEN}=== Deployment setup complete! ===${NC}"

