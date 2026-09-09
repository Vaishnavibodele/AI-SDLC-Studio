#!/usr/bin/env bash
# ==============================================================================
# AI SDLC Studio - Amazon S3 Frontend Build & Deployment Script
# Builds the Vite React SPA and syncs static assets to Amazon S3
# ==============================================================================

set -e

if [ -z "$1" ]; then
    echo "❌ Error: Missing S3 bucket name argument."
    echo "Usage: ./deploy_s3.sh <S3_BUCKET_NAME> [AWS_REGION] [EC2_BACKEND_IP_OR_DOMAIN]"
    echo "Example: ./deploy_s3.sh my-ai-sdlc-portal-bucket us-east-1 54.210.30.120"
    exit 1
fi

S3_BUCKET="$1"
AWS_REGION="${2:-us-east-1}"
EC2_BACKEND="${3:-}"

echo "=========================================================="
echo "🚀 Building & Deploying Frontend to Amazon S3"
echo "Bucket: s3://${S3_BUCKET}"
echo "Region: ${AWS_REGION}"
echo "=========================================================="

# Navigate to frontend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/../frontend"

cd "${FRONTEND_DIR}"

# If EC2 Backend IP provided, configure production .env
if [ -n "${EC2_BACKEND}" ]; then
    echo "🔧 Updating .env.production with Backend URL: http://${EC2_BACKEND}:8000/api"
    cat <<EOF > .env.production
VITE_API_BASE=http://${EC2_BACKEND}:8000/api
VITE_STUDIO_API_KEY=default_secret_key_12345
EOF
fi

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

# Build static bundle for production
echo "🔨 Building production static bundle with Vite..."
npm run build

echo "☁️ Syncing dist/ assets to Amazon S3 Bucket: ${S3_BUCKET}..."
aws s3 sync dist/ "s3://${S3_BUCKET}" \
    --region "${AWS_REGION}" \
    --delete \
    --cache-control "max-age=31536000,public" \
    --exclude "index.html"

# Upload index.html with no-cache so browsers always get fresh version
aws s3 cp dist/index.html "s3://${S3_BUCKET}/index.html" \
    --region "${AWS_REGION}" \
    --cache-control "no-cache, no-store, must-revalidate"

echo ""
echo "=========================================================="
echo "🎉 Frontend Deployment to S3 Completed Successfully!"
echo "S3 Website URL: http://${S3_BUCKET}.s3-website-${AWS_REGION}.amazonaws.com"
echo "=========================================================="
