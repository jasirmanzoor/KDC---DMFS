# KDC DMFS — Railway Deployment Guide
# 15 minutes from zero to live

## STEP 1: Create Railway project (5 min)

1. Go to https://railway.app → sign in with GitHub
2. Click "New Project" → "Empty Project"
3. Click "Add Service" → "Database" → "PostgreSQL"
4. Railway creates a Postgres instance automatically
5. Click the Postgres service → "Variables" tab
6. Copy the `DATABASE_URL` value

## STEP 2: Deploy the backend (5 min)

1. In your Railway project → "Add Service" → "GitHub Repo"
2. Connect your GitHub and select this repository
3. Railway auto-detects the `railway.toml` and deploys
4. In the service → "Variables" tab → add:
   ```
   DATABASE_URL = (paste from step 1)
   PORT = 8000
   ```
5. The service deploys automatically
6. Click the service → "Settings" → copy the public URL
   (looks like: https://kdc-dmfs-production.up.railway.app)

## STEP 3: Run database migrations (1 min)

In Railway dashboard → your Postgres service → "Query" tab, paste and run:
(contents of migrations/001_schema.sql)

Or via CLI:
```bash
psql "$DATABASE_URL" -f migrations/001_schema.sql
```

## STEP 4: Deploy the frontend (4 min)

1. In Railway → "Add Service" → "GitHub Repo" (same repo)
2. Set root directory to `frontend`
3. Add variable:
   ```
   VITE_API_URL = https://your-backend-url.up.railway.app
   ```
4. Build command: `npm install && npm run build`
5. Start command: `npx serve dist -p $PORT`

## STEP 5: Verify everything works

1. Open your frontend URL
2. Go to "Import & Sync" → click "Sync Drivers"
3. Watch the log — should show 2,652+ drivers synced
4. Go to "Drivers" — should show all your real drivers with station, IBAN, DA codes
5. Create a payroll cycle → calculate → verify math

## ENVIRONMENT VARIABLES SUMMARY

Backend:
- DATABASE_URL (from Railway Postgres)
- PORT (auto-set by Railway)

Frontend:
- VITE_API_URL (your backend Railway URL)

## API ENDPOINTS

GET  /health                          — health check + driver count
GET  /api/dashboard                   — owner dashboard stats
GET  /api/drivers?search=&vendor=     — driver list with filters
GET  /api/drivers/{nid}               — full driver detail
POST /api/drivers                     — create driver
PUT  /api/drivers/{nid}               — update driver
POST /api/sync/drivers                — sync from Google Sheets (background job)
GET  /api/sync/status/{log_id}        — check sync progress
GET  /api/sync/latest                 — recent sync history
POST /api/payroll/calculate/{cycle_id}— calculate payroll (dry run)
POST /api/payroll/finalize/{cycle_id} — finalize and save payroll
GET  /api/deductions?national_id=     — deduction list
POST /api/deductions                  — create deduction
GET  /api/pn-requests                 — PN request list (auto-expires overdue)
PUT  /api/pn-requests/{id}/approve    — approve PN + activate driver
GET  /api/loan-requests               — loan request list
POST /api/loan-requests               — create loan request (auto background check)
GET  /api/export/payroll/{cycle_id}   — download payroll CSV
