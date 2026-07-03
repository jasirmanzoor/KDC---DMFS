#!/bin/bash
# KDC DMFS — One-command setup
# Usage: DATABASE_URL=postgresql://... bash setup.sh

set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  KDC DMFS — Production Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "$DATABASE_URL" ]; then
  echo "❌ DATABASE_URL not set"
  echo "   Export it first: export DATABASE_URL=postgresql://user:pass@host:5432/dbname"
  exit 1
fi

echo "✅ DATABASE_URL found"
echo ""
echo "📦 Running database migrations..."
psql "$DATABASE_URL" -f migrations/001_schema.sql
echo "✅ Schema created"
echo ""
echo "📦 Installing Python dependencies..."
cd backend && pip install -r requirements.txt -q
echo "✅ Dependencies installed"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo ""
echo "To start the server:"
echo "  cd backend && uvicorn main:app --reload"
echo ""
echo "To sync drivers from Google Sheets:"
echo "  curl -X POST http://localhost:8000/api/sync/drivers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
