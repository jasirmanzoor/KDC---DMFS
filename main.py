"""
KDC DMFS — FastAPI Backend
Complete production API for Driver Management & Financial Settlements
"""
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import asyncpg
import os
import io
import csv
import json
import httpx
from datetime import date, datetime, timedelta
from typing import Optional, List
from decimal import Decimal

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/kdc_dmfs")
SHEET_ID = "1WzWa3UtzcAlnmt76cwUeQhd7K8kfiFa8fnVWgQEatoU"

# ── Payroll constants ──────────────────────────────────────────
BANK_FEE = Decimal("8.50")
PN_FEE   = Decimal("100.00")
MAX_CAP  = Decimal("0.60")

DEDUCTION_PRIORITY = {
    "Violation": 10, "DFS_Amount": 12, "Liability": 15,
    "Pending_Naifaz": 20, "Loan_Petro_App": 35, "Loan_Future_App": 40,
    "Loan": 40, "Advance_Salary": 50, "Credit_Note": 60, "Carried_Down": 60,
}

# ── Hiring sheet exact column positions (confirmed from diagnostic) ──
COL = {
    "timestamp": 0, "vendor": 1, "city": 2, "station": 3,
    "mobile": 4, "nid": 5, "name_ar": 6, "emp_status": 7,
    "name_en": 8, "email": 9, "nationality": 10,
    "bank_name": 16, "account_number": 17, "account_nid": 18,
    "bank_status": 19, "pn_number": 20, "keeta_sub": 21,
    "pns_status": 22, "pn_date": 23, "deposition": 24,
    "fee_amount": 25, "received": 26, "remaining": 27,
    "da_type": 30, "supervisor_target": 31, "all_ids": 32,
    "imile_id": 33, "amazon_id": 34, "noon_id": 35,
    "jnt_id": 36, "landmark_id": 37, "ajex_id": 38,
    "naqel_id": 39, "keeta_id": 40, "keeta_target": 41,
    "basic_salary": 42,
}

pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    yield
    await pool.close()

app = FastAPI(title="KDC DMFS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])

async def db() -> asyncpg.Pool:
    return pool

# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM drivers")
    return {"status": "ok", "drivers": count, "time": datetime.now().isoformat()}

# ═══════════════════════════════════════════════════════════════
# DRIVERS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/drivers")
async def list_drivers(
    search: Optional[str] = None,
    vendor: Optional[str] = None,
    station: Optional[str] = None,
    status: Optional[str] = None,
    pns: Optional[str] = None,
    da_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    conditions = ["1=1"]
    params = []
    i = 1

    if search:
        conditions.append(f"(national_id ILIKE ${i} OR name_ar ILIKE ${i} OR name_en ILIKE ${i} OR mobile ILIKE ${i} OR da_code ILIKE ${i})")
        params.append(f"%{search}%"); i += 1
    if vendor:
        conditions.append(f"vendor_code = ${i}"); params.append(vendor); i += 1
    if station:
        conditions.append(f"station_name ILIKE ${i}"); params.append(f"%{station}%"); i += 1
    if status:
        conditions.append(f"employment_status = ${i}"); params.append(status); i += 1
    if pns:
        conditions.append(f"pns_status = ${i}"); params.append(pns); i += 1
    if da_type:
        conditions.append(f"da_type = ${i}"); params.append(da_type); i += 1

    where = " AND ".join(conditions)
    offset = (page - 1) * limit

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM drivers WHERE {where}", *params)
        rows = await conn.fetch(
            f"""SELECT id, national_id, name_ar, name_en, mobile, email,
                       vendor_code, station_name, city, da_type, da_code,
                       imile_id, ajex_id, naqel_id, keeta_id, jnt_id, landmark_id,
                       employment_status, pns_status, pn_number,
                       bank_name, iban_number, basic_salary,
                       naafiz_fee, naafiz_received, naafiz_remaining,
                       first_payment_processed, hired_date, created_at
                FROM drivers WHERE {where}
                ORDER BY name_ar NULLS LAST
                LIMIT ${i} OFFSET ${i+1}""",
            *params, limit, offset
        )

    return {
        "total": total, "page": page, "limit": limit,
        "pages": (total + limit - 1) // limit,
        "data": [dict(r) for r in rows]
    }

@app.get("/api/drivers/{nid}")
async def get_driver(nid: str):
    async with pool.acquire() as conn:
        driver = await conn.fetchrow("SELECT * FROM drivers WHERE national_id = $1", nid)
        if not driver:
            raise HTTPException(404, f"Driver {nid} not found")

        deductions = await conn.fetch(
            "SELECT * FROM deductions WHERE national_id = $1 AND status = 'active' ORDER BY priority",
            nid
        )
        payroll_history = await conn.fetch(
            """SELECT pi.*, pc.cycle_name, pc.period_start, pc.period_end
               FROM payroll_items pi
               JOIN payroll_cycles pc ON pc.id = pi.cycle_id
               WHERE pi.national_id = $1
               ORDER BY pc.period_start DESC LIMIT 10""",
            nid
        )
        pn_requests = await conn.fetch(
            "SELECT * FROM pn_requests WHERE national_id = $1 ORDER BY created_at DESC LIMIT 5",
            nid
        )
        loan_requests = await conn.fetch(
            "SELECT * FROM loan_requests WHERE national_id = $1 ORDER BY created_at DESC LIMIT 5",
            nid
        )
        outstanding = await conn.fetchval(
            "SELECT COALESCE(SUM(remaining_balance), 0) FROM deductions WHERE national_id = $1 AND status = 'active'",
            nid
        )

    return {
        "driver": dict(driver),
        "deductions": [dict(r) for r in deductions],
        "payroll_history": [dict(r) for r in payroll_history],
        "pn_requests": [dict(r) for r in pn_requests],
        "loan_requests": [dict(r) for r in loan_requests],
        "total_outstanding": float(outstanding or 0),
    }

@app.post("/api/drivers")
async def create_driver(data: dict):
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM drivers WHERE national_id = $1", data["national_id"]
        )
        if existing:
            raise HTTPException(400, f"Driver {data['national_id']} already exists")

        # Detect SBY_DS03
        station = data.get("station_name", "")
        if "SBY" in station.upper() or "DS03" in station.upper():
            data["vendor_code"] = "SBY_DS03"

        cols = [k for k in data if k != "id"]
        placeholders = [f"${i+1}" for i in range(len(cols))]
        vals = [data[c] for c in cols]

        driver_id = await conn.fetchval(
            f"INSERT INTO drivers ({','.join(cols)}) VALUES ({','.join(placeholders)}) RETURNING id",
            *vals
        )
    return {"id": str(driver_id), "national_id": data["national_id"]}

@app.put("/api/drivers/{nid}")
async def update_driver(nid: str, data: dict):
    data.pop("id", None)
    data.pop("national_id", None)
    if not data:
        raise HTTPException(400, "No fields to update")

    sets = [f"{k} = ${i+1}" for i, k in enumerate(data)]
    vals = list(data.values()) + [nid]

    async with pool.acquire() as conn:
        result = await conn.execute(
            f"UPDATE drivers SET {', '.join(sets)} WHERE national_id = ${len(vals)}",
            *vals
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "Driver not found")
    return {"updated": True}

# ═══════════════════════════════════════════════════════════════
# GOOGLE SHEETS SYNC
# ═══════════════════════════════════════════════════════════════

def parse_csv(text: str) -> list[list[str]]:
    """Parse CSV text into list of rows (list of cells)."""
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]

def c(row: list, idx: int) -> str:
    """Safe cell getter."""
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx]).strip()

def n(row: list, idx: int) -> Decimal:
    """Safe numeric cell getter."""
    v = c(row, idx).replace(",", "").replace("$", "")
    try:
        return Decimal(v)
    except:
        return Decimal("0")

def detect_status(raw: str, field: str) -> str:
    raw = raw.lower().strip()
    if field == "employment":
        if "hold" in raw or "موقوف" in raw: return "hold"
        if "terminat" in raw or "منتهي" in raw or "closed" in raw: return "terminated"
        if "suspend" in raw: return "suspended"
        if "pending_pn" in raw: return "pending_pn"
        return "active"
    if field == "pns":
        if raw == "approved": return "approved"
        if raw in ("closed", "cancelled_by_creditor", "cancelled", "expired"): return "expired"
        if raw == "rejected": return "rejected"
        return "pending"
    if field == "da_type":
        if "fixed" in raw: return "Fixed_Salary"
        if "owan" in raw or "target" in raw or "keeta" in raw: return "Salary_Owan"
        return "Per_Packet"
    return raw

@app.post("/api/sync/drivers")
async def sync_drivers(background_tasks: BackgroundTasks):
    """Sync all drivers from KDC Hiring sheet (GID 1866027856)."""
    log_id = None
    async with pool.acquire() as conn:
        log_id = await conn.fetchval(
            """INSERT INTO sheets_sync_log (sync_type, sheet_name, status, triggered_by)
               VALUES ('drivers', 'Hiring (GID:1866027856)', 'running', 'api')
               RETURNING id"""
        )

    background_tasks.add_task(_sync_drivers_task, str(log_id))
    return {"message": "Sync started", "log_id": str(log_id)}

async def _sync_drivers_task(log_id: str):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=1866027856"
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

        if "<html" in text.lower() or "sign in" in text.lower():
            raise Exception("Sheet not accessible — ensure 'Publish to web' is enabled")

        rows = parse_csv(text)

        # Find data start row
        data_start = 1
        for i, row in enumerate(rows[:5]):
            if len(row) > 5 and len(c(row, COL["nid"]).replace(" ","")) == 10:
                data_start = i
                break

        async with pool.acquire() as conn:
            for i, row in enumerate(rows[data_start:], start=data_start):
                try:
                    nid = c(row, COL["nid"]).replace(" ", "").replace(",", "")
                    if not (nid.isdigit() and len(nid) == 10):
                        stats["skipped"] += 1
                        continue

                    # Parse fields using confirmed column positions
                    iban_raw = c(row, COL["account_number"]).replace(" ","").replace("-","")
                    iban = iban_raw.upper() if (iban_raw.upper().startswith("SA") and len(iban_raw) >= 20) else ""

                    naafiz_fee = n(row, COL["fee_amount"]) or Decimal("100")
                    naafiz_rcv = n(row, COL["received"])
                    naafiz_rem = n(row, COL["remaining"])
                    deposition = c(row, COL["deposition"]).lower()
                    first_paid = ("deducted" in deposition and "from first" not in deposition and naafiz_rem == 0)

                    pn_raw = c(row, COL["pn_number"])
                    # Clean scientific notation
                    try:
                        pn_clean = str(int(float(pn_raw))) if pn_raw and "E" in pn_raw.upper() else pn_raw
                    except:
                        pn_clean = pn_raw

                    vendor = c(row, COL["vendor"])
                    imile_id = c(row, COL["imile_id"])
                    ajex_id  = c(row, COL["ajex_id"])
                    naqel_id = c(row, COL["naqel_id"])
                    keeta_id = c(row, COL["keeta_id"])
                    jnt_id   = c(row, COL["jnt_id"])
                    lm_id    = c(row, COL["landmark_id"])
                    da_code  = imile_id or ajex_id or naqel_id or keeta_id or jnt_id or lm_id or ""

                    if not vendor or vendor.upper() in ("KDC", ""):
                        if imile_id: vendor = "iMile"
                        elif ajex_id: vendor = "Ajex"
                        elif naqel_id: vendor = "Naqel"
                        elif keeta_id: vendor = "Keeta"
                        elif jnt_id: vendor = "J&T"
                        elif lm_id: vendor = "Landmark"
                        else: vendor = "iMile"

                    station = c(row, COL["station"])
                    city    = c(row, COL["city"])
                    if not station and city and "غير موجود" not in city:
                        station = city

                    # SBY_DS03 detection
                    if "SBY" in station.upper() or "DS03" in station.upper():
                        vendor = "SBY_DS03"

                    basic_sal_raw = n(row, COL["basic_salary"])
                    keeta_tgt_raw = n(row, COL["keeta_target"])

                    driver_data = {
                        "national_id": nid,
                        "name_ar": c(row, COL["name_ar"]),
                        "name_en": c(row, COL["name_en"]),
                        "vendor_code": vendor,
                        "city": city,
                        "station_name": station,
                        "mobile": c(row, COL["mobile"]),
                        "email": c(row, COL["email"]),
                        "nationality": c(row, COL["nationality"]),
                        "bank_name": c(row, COL["bank_name"]),
                        "iban_number": iban,
                        "pns_status": detect_status(c(row, COL["pns_status"]), "pns"),
                        "employment_status": detect_status(c(row, COL["emp_status"]), "employment"),
                        "da_type": detect_status(c(row, COL["da_type"]), "da_type"),
                        "da_code": da_code,
                        "imile_id": imile_id,
                        "ajex_id": ajex_id,
                        "naqel_id": naqel_id,
                        "keeta_id": keeta_id,
                        "jnt_id": jnt_id,
                        "landmark_id": lm_id,
                        "pn_number": pn_clean,
                        "naafiz_fee": float(naafiz_fee),
                        "naafiz_received": float(naafiz_rcv),
                        "naafiz_remaining": float(naafiz_rem),
                        "first_payment_processed": first_paid,
                        "pn_fee_deducted": first_paid,
                        "source": "sheets_import",
                    }
                    if basic_sal_raw > 0:
                        driver_data["basic_salary"] = float(basic_sal_raw)
                    if keeta_tgt_raw > 0:
                        driver_data["keeta_target"] = int(keeta_tgt_raw)

                    # Upsert — INSERT ON CONFLICT UPDATE
                    cols = list(driver_data.keys())
                    vals = [driver_data[k] for k in cols]
                    placeholders = [f"${j+1}" for j in range(len(cols))]
                    update_sets = [f"{k} = EXCLUDED.{k}" for k in cols if k != "national_id"]

                    result = await conn.fetchrow(
                        f"""INSERT INTO drivers ({','.join(cols)})
                            VALUES ({','.join(placeholders)})
                            ON CONFLICT (national_id) DO UPDATE SET
                            {', '.join(update_sets)},
                            updated_at = NOW()
                            RETURNING (xmax = 0) AS is_insert""",
                        *vals
                    )
                    if result["is_insert"]:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                except Exception as row_err:
                    stats["errors"].append(f"Row {i}: {str(row_err)}")

        # Update sync log
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE sheets_sync_log SET
                   status = 'completed', rows_read = $1,
                   records_created = $2, records_updated = $3,
                   records_skipped = $4, errors_count = $5,
                   error_log = $6, completed_at = NOW()
                   WHERE id = $7""",
                stats["created"] + stats["updated"] + stats["skipped"],
                stats["created"], stats["updated"], stats["skipped"],
                len(stats["errors"]),
                json.dumps(stats["errors"][:20]),
                log_id
            )

    except Exception as e:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE sheets_sync_log SET status='failed', error_log=$1, completed_at=NOW() WHERE id=$2",
                json.dumps([str(e)]), log_id
            )

@app.get("/api/sync/status/{log_id}")
async def sync_status(log_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sheets_sync_log WHERE id = $1", log_id)
    if not row:
        raise HTTPException(404, "Sync log not found")
    return dict(row)

@app.get("/api/sync/latest")
async def latest_syncs():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM sheets_sync_log ORDER BY started_at DESC LIMIT 10"
        )
    return [dict(r) for r in rows]

# ═══════════════════════════════════════════════════════════════
# PAYROLL ENGINE
# ═══════════════════════════════════════════════════════════════

def calculate_gross(driver: dict, pricing: dict, delivery: dict) -> tuple[Decimal, dict]:
    da_type = driver.get("da_type", "Per_Packet")

    if da_type == "Per_Packet":
        ppd = Decimal(str(delivery.get("ppd_dld", 0)))
        cod = Decimal(str(delivery.get("cod_dld", 0)))
        rev = Decimal(str(delivery.get("reverse_dld", 0)))
        ppd_price = Decimal(str(pricing.get("ppd_price", 0)))
        cod_price = Decimal(str(pricing.get("cod_price", 0)))
        rev_price = Decimal(str(pricing.get("reverse_price", 0)))
        ppd_earn = ppd * ppd_price
        cod_earn = cod * cod_price
        rev_earn = rev * rev_price
        gross = ppd_earn + cod_earn + rev_earn
        return gross, {
            "method": "Per_Packet",
            "ppd": {"count": int(ppd), "rate": float(ppd_price), "amount": float(ppd_earn)},
            "cod": {"count": int(cod), "rate": float(cod_price), "amount": float(cod_earn)},
            "reverse": {"count": int(rev), "rate": float(rev_price), "amount": float(rev_earn)},
        }

    if da_type == "Fixed_Salary":
        basic = Decimal(str(driver.get("basic_salary") or 0))
        gross = basic / 2
        return gross, {"method": "Fixed_Salary", "monthly": float(basic), "biweekly": float(gross)}

    if da_type == "Salary_Owan":
        base = Decimal(str(pricing.get("basic_salary_keeta") or driver.get("basic_salary") or 2500))
        target = Decimal(str(pricing.get("target_orders_keeta") or driver.get("keeta_target") or 450))
        bonus_rate = Decimal(str(pricing.get("bonus_per_excess") or 10))
        penalty_rate = Decimal(str(pricing.get("penalty_per_deficit") or 10))
        orders = Decimal(str(delivery.get("orders_delivered", 0)))
        diff = orders - target
        bonus = max(Decimal("0"), diff * bonus_rate) if diff > 0 else Decimal("0")
        penalty = max(Decimal("0"), abs(diff) * penalty_rate) if diff < 0 else Decimal("0")
        gross = max(Decimal("0"), base + bonus - penalty)
        return gross, {
            "method": "Salary_Owan", "base": float(base), "target": int(target),
            "orders": int(orders), "diff": int(diff),
            "bonus": float(bonus), "penalty": float(penalty),
        }

    return Decimal("0"), {"method": "Unknown"}

def apply_deductions(gross: Decimal, deductions: list, is_first_payment: bool, status: str) -> dict:
    bank_fee = BANK_FEE
    pn_fee   = PN_FEE if is_first_payment else Decimal("0")
    fixed    = bank_fee + pn_fee

    max_kdc     = gross * MAX_CAP
    remaining   = max_kdc
    applied     = []
    total_kdc   = Decimal("0")
    cap_hit     = False

    sorted_deds = sorted(
        [d for d in deductions if d.get("status") == "active" and (d.get("remaining_balance") or 0) > 0],
        key=lambda d: DEDUCTION_PRIORITY.get(d.get("deduction_type",""), 99)
    )

    for ded in sorted_deds:
        if remaining <= Decimal("0.01"):
            cap_hit = True
            break
        installment = Decimal(str(ded.get("installment_amount") or 0))
        balance     = Decimal(str(ded.get("remaining_balance") or 0))
        requested   = min(installment, balance)
        if requested <= 0:
            continue
        amt = min(requested, remaining)
        applied.append({
            "deduction_id":   str(ded.get("id", "")),
            "deduction_type": ded["deduction_type"],
            "priority":       DEDUCTION_PRIORITY.get(ded["deduction_type"], 99),
            "requested":      float(requested),
            "applied":        float(amt),
            "was_capped":     amt < requested,
            "remaining_before": float(balance),
            "remaining_after":  float(max(Decimal("0"), balance - amt)),
        })
        total_kdc += amt
        remaining -= amt

    if total_kdc >= max_kdc - Decimal("0.01") and max_kdc > 0:
        cap_hit = True

    total_deductions = fixed + total_kdc
    net = max(Decimal("0"), gross - total_deductions)

    return {
        "bank_fee":           float(bank_fee),
        "pn_fee":             float(pn_fee),
        "is_first_payment":   is_first_payment,
        "kdc_deductions":     applied,
        "total_kdc":          float(total_kdc),
        "total_deductions":   float(total_deductions),
        "net_payable":        float(net),
        "cap_applied":        cap_hit,
        "cap_amount":         float(max_kdc),
        "cap_pct":            int((total_kdc / max_kdc * 100)) if max_kdc > 0 else 0,
        "payment_status":     "held" if status == "hold" else "pending",
    }

@app.post("/api/payroll/calculate/{cycle_id}")
async def calculate_payroll(cycle_id: str):
    """Calculate full payroll for a cycle. Returns results without saving."""
    async with pool.acquire() as conn:
        cycle = await conn.fetchrow("SELECT * FROM payroll_cycles WHERE id = $1", cycle_id)
        if not cycle:
            raise HTTPException(404, "Cycle not found")

        drivers = await conn.fetch(
            """SELECT d.*, dr.ppd_dld, dr.cod_dld, dr.reverse_dld, dr.orders_delivered,
                      dr.ppd_price, dr.cod_price, dr.reverse_price
               FROM drivers d
               LEFT JOIN delivery_records dr ON dr.national_id = d.national_id AND dr.cycle_id = $1
               WHERE d.employment_status IN ('active', 'hold')""",
            cycle_id
        )

        all_deductions = await conn.fetch(
            "SELECT * FROM deductions WHERE status = 'active' AND remaining_balance > 0"
        )
        ded_map = {}
        for ded in all_deductions:
            nid = ded["national_id"]
            if nid not in ded_map:
                ded_map[nid] = []
            ded_map[nid].append(dict(ded))

        pricing_rows = await conn.fetch(
            "SELECT * FROM station_pricing WHERE is_active = true"
        )
        pricing_map = {}
        for p in pricing_rows:
            key = (p["vendor_code"], p["station_name"])
            pricing_map[key] = dict(p)

    results = []
    warnings = []

    for driver in drivers:
        d = dict(driver)
        nid = d["national_id"]

        # Find pricing
        pricing = (
            pricing_map.get((d["vendor_code"], d["station_name"])) or
            pricing_map.get((d["vendor_code"], None)) or
            {}
        )
        if not pricing and d["da_type"] == "Per_Packet":
            warnings.append(f"No pricing for {nid} ({d['vendor_code']}/{d['station_name']})")

        delivery = {
            "ppd_dld": d.get("ppd_dld") or 0,
            "cod_dld": d.get("cod_dld") or 0,
            "reverse_dld": d.get("reverse_dld") or 0,
            "orders_delivered": d.get("orders_delivered") or 0,
        }
        if pricing:
            delivery["ppd_price"] = pricing.get("ppd_price", 0)
            delivery["cod_price"] = pricing.get("cod_price", 0)
            delivery["reverse_price"] = pricing.get("reverse_price", 0)

        gross, gross_bd = calculate_gross(d, pricing, delivery)
        ded_result = apply_deductions(
            gross,
            ded_map.get(nid, []),
            not d.get("first_payment_processed", True),
            d.get("employment_status", "active")
        )

        results.append({
            "national_id":     nid,
            "driver_name_ar":  d.get("name_ar", ""),
            "driver_name_en":  d.get("name_en", ""),
            "vendor_code":     d.get("vendor_code", ""),
            "station_name":    d.get("station_name", ""),
            "da_type":         d.get("da_type", ""),
            "da_code":         d.get("da_code", ""),
            "bank_name":       d.get("bank_name", ""),
            "iban_number":     d.get("iban_number", ""),
            "ppd_count":       int(delivery["ppd_dld"]),
            "cod_count":       int(delivery["cod_dld"]),
            "reverse_count":   int(delivery["reverse_dld"]),
            "orders_count":    int(delivery["orders_delivered"]),
            "gross_salary":    float(gross),
            "gross_breakdown": gross_bd,
            **ded_result,
        })

    totals = {
        "drivers":    len(results),
        "gross":      sum(r["gross_salary"] for r in results),
        "deductions": sum(r["total_deductions"] for r in results),
        "net":        sum(r["net_payable"] for r in results),
        "held":       sum(r["net_payable"] for r in results if r["payment_status"] == "held"),
    }

    return {"cycle": dict(cycle), "results": results, "totals": totals, "warnings": warnings}

@app.post("/api/payroll/finalize/{cycle_id}")
async def finalize_payroll(cycle_id: str):
    """Save payroll results and update deduction balances."""
    calc = await calculate_payroll(cycle_id)
    results = calc["results"]
    totals  = calc["totals"]

    async with pool.acquire() as conn:
        async with conn.transaction():
            for r in results:
                nid = r["national_id"]

                # Save payroll item
                await conn.execute(
                    """INSERT INTO payroll_items (
                        cycle_id, national_id, driver_name_ar, driver_name_en,
                        vendor_code, station_name, da_type, da_code,
                        bank_name, iban_number,
                        ppd_count, cod_count, reverse_count, orders_count,
                        gross_salary, gross_breakdown,
                        bank_fee, pn_fee, is_first_payment,
                        kdc_deductions, total_kdc_deductions,
                        total_deductions, net_payable,
                        deduction_cap_applied, deduction_cap_pct,
                        payment_status, finalized_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                        $11,$12,$13,$14,$15,$16,$17,$18,$19,
                        $20,$21,$22,$23,$24,$25,$26,NOW()
                    ) ON CONFLICT (cycle_id, national_id) DO UPDATE SET
                        gross_salary = EXCLUDED.gross_salary,
                        net_payable  = EXCLUDED.net_payable,
                        total_deductions = EXCLUDED.total_deductions,
                        kdc_deductions = EXCLUDED.kdc_deductions,
                        payment_status = EXCLUDED.payment_status,
                        finalized_at = NOW()""",
                    cycle_id, nid,
                    r["driver_name_ar"], r["driver_name_en"],
                    r["vendor_code"], r["station_name"],
                    r["da_type"], r["da_code"],
                    r["bank_name"], r["iban_number"],
                    r["ppd_count"], r["cod_count"],
                    r["reverse_count"], r["orders_count"],
                    r["gross_salary"], json.dumps(r["gross_breakdown"]),
                    r["bank_fee"], r["pn_fee"], r["is_first_payment"],
                    json.dumps(r["kdc_deductions"]), r["total_kdc"],
                    r["total_deductions"], r["net_payable"],
                    r["cap_applied"], r["cap_pct"],
                    r["payment_status"]
                )

                # Update deduction balances
                for ded in r.get("kdc_deductions", []):
                    if ded["applied"] > 0:
                        new_remaining = ded["remaining_after"]
                        new_status = "completed" if new_remaining <= 0 else "active"
                        await conn.execute(
                            """UPDATE deductions SET
                               remaining_balance = $1, status = $2, updated_at = NOW(),
                               completed_at = CASE WHEN $2 = 'completed' THEN NOW() ELSE completed_at END
                               WHERE id = $3""",
                            new_remaining, new_status, ded["deduction_id"]
                        )

                # Mark first payment processed
                if r["is_first_payment"]:
                    await conn.execute(
                        "UPDATE drivers SET first_payment_processed = true, pn_fee_deducted = true WHERE national_id = $1",
                        nid
                    )
                    # Mark PN fee as deducted
                    await conn.execute(
                        "UPDATE pn_requests SET fee_status = 'deducted' WHERE national_id = $1 AND fee_status = 'not_deducted'",
                        nid
                    )

                # Record transaction
                await conn.execute(
                    """INSERT INTO transactions (
                        national_id, driver_name, cycle_id,
                        transaction_date, direction, amount,
                        category, description, payment_method, status
                    ) VALUES ($1,$2,$3,$4,'money_out',$5,'driver_salary',$6,'bank_transfer','completed')""",
                    nid, r["driver_name_ar"] or r["driver_name_en"],
                    cycle_id, date.today(),
                    r["net_payable"],
                    f"Salary — {r.get('vendor_code','')} — {r.get('station_name','')}"
                )

            # Update cycle totals
            await conn.execute(
                """UPDATE payroll_cycles SET
                   status = 'paid', total_drivers = $1,
                   total_gross = $2, total_deductions = $3,
                   total_net = $4, total_held = $5,
                   finalized_at = NOW(), updated_at = NOW()
                   WHERE id = $6""",
                totals["drivers"], totals["gross"],
                totals["deductions"], totals["net"],
                totals["held"], cycle_id
            )

    return {"finalized": True, "totals": totals, "drivers_processed": len(results)}

# ═══════════════════════════════════════════════════════════════
# DEDUCTIONS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/deductions")
async def list_deductions(
    national_id: Optional[str] = None,
    deduction_type: Optional[str] = None,
    status: str = "active",
    page: int = 1, limit: int = 50
):
    conditions = ["1=1"]
    params = []
    i = 1
    if national_id:
        conditions.append(f"national_id = ${i}"); params.append(national_id); i += 1
    if deduction_type:
        conditions.append(f"deduction_type = ${i}"); params.append(deduction_type); i += 1
    if status:
        conditions.append(f"status = ${i}"); params.append(status); i += 1

    where = " AND ".join(conditions)
    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM deductions WHERE {where}", *params)
        rows  = await conn.fetch(
            f"""SELECT d.*, dr.name_ar, dr.name_en, dr.vendor_code, dr.station_name
                FROM deductions d
                LEFT JOIN drivers dr USING(national_id)
                WHERE {where}
                ORDER BY d.priority, d.created_at
                LIMIT ${i} OFFSET ${i+1}""",
            *params, limit, (page-1)*limit
        )
        summary = await conn.fetchrow(
            """SELECT
               COALESCE(SUM(CASE WHEN deduction_type LIKE 'Loan%' THEN remaining_balance END),0) AS total_loans,
               COALESCE(SUM(CASE WHEN deduction_type = 'Credit_Note' THEN remaining_balance END),0) AS total_cn,
               COALESCE(SUM(CASE WHEN deduction_type = 'DFS_Amount' THEN remaining_balance END),0) AS total_dfs,
               COALESCE(SUM(CASE WHEN deduction_type = 'Violation' THEN remaining_balance END),0) AS total_violations,
               COALESCE(SUM(remaining_balance),0) AS grand_total
               FROM deductions WHERE status = 'active'"""
        )
    return {
        "total": total, "data": [dict(r) for r in rows],
        "summary": dict(summary)
    }

@app.post("/api/deductions")
async def create_deduction(data: dict):
    data["priority"] = DEDUCTION_PRIORITY.get(data.get("deduction_type",""), 40)
    data["remaining_balance"] = data.get("remaining_balance", data.get("amount", 0))
    cols = list(data.keys())
    vals = [data[k] for k in cols]
    async with pool.acquire() as conn:
        did = await conn.fetchval(
            f"INSERT INTO deductions ({','.join(cols)}) VALUES ({','.join(f'${j+1}' for j in range(len(cols)))}) RETURNING id",
            *vals
        )
    return {"id": str(did)}

# ═══════════════════════════════════════════════════════════════
# PN REQUESTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/pn-requests")
async def list_pn_requests(status: Optional[str] = None):
    where = "WHERE pr.naafiz_status = $1" if status else ""
    params = [status] if status else []
    async with pool.acquire() as conn:
        # Auto-expire past-due PNs
        await conn.execute(
            """UPDATE pn_requests SET naafiz_status='expired', fee_status='wasted'
               WHERE expiry_date < CURRENT_DATE
               AND naafiz_status NOT IN ('approved','rejected','expired')"""
        )
        rows = await conn.fetch(
            f"""SELECT pr.*,
                       (pr.expiry_date - CURRENT_DATE) AS days_remaining
                FROM pn_requests pr
                {where}
                ORDER BY (pr.expiry_date - CURRENT_DATE) ASC NULLS LAST""",
            *params
        )
        stats = await conn.fetchrow(
            """SELECT
               COUNT(*) FILTER (WHERE naafiz_status IN ('pending','submitted')) AS active,
               COUNT(*) FILTER (WHERE expiry_date = CURRENT_DATE AND naafiz_status NOT IN ('approved','expired')) AS expiring_today,
               COUNT(*) FILTER (WHERE expiry_date <= CURRENT_DATE + 3 AND naafiz_status NOT IN ('approved','expired')) AS expiring_3days,
               COUNT(*) FILTER (WHERE naafiz_status = 'approved') AS approved,
               COALESCE(SUM(fee_amount) FILTER (WHERE fee_status = 'wasted'),0) AS wasted_fees
               FROM pn_requests"""
        )
    return {"data": [dict(r) for r in rows], "stats": dict(stats)}

@app.put("/api/pn-requests/{pn_id}/approve")
async def approve_pn(pn_id: str):
    async with pool.acquire() as conn:
        pn = await conn.fetchrow("SELECT * FROM pn_requests WHERE id = $1", pn_id)
        if not pn:
            raise HTTPException(404, "PN Request not found")
        await conn.execute(
            """UPDATE pn_requests SET naafiz_status='approved', approved_date=CURRENT_DATE, updated_at=NOW()
               WHERE id = $1""", pn_id
        )
        await conn.execute(
            """UPDATE drivers SET pns_status='approved',
               employment_status = CASE WHEN employment_status='pending_pn' THEN 'active' ELSE employment_status END,
               updated_at=NOW()
               WHERE national_id = $1""",
            pn["national_id"]
        )
    return {"approved": True}

# ═══════════════════════════════════════════════════════════════
# LOAN REQUESTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/loan-requests")
async def list_loans(status: Optional[str] = None, page: int = 1, limit: int = 50):
    where = "WHERE final_status = $1" if status else ""
    params = [status] if status else []
    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM loan_requests {where}", *params)
        rows  = await conn.fetch(
            f"SELECT * FROM loan_requests {where} ORDER BY created_at DESC LIMIT ${ len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, (page-1)*limit
        )
    return {"total": total, "data": [dict(r) for r in rows]}

@app.post("/api/loan-requests")
async def create_loan_request(data: dict):
    """Create loan request with automatic background check."""
    nid = data["national_id"]

    async with pool.acquire() as conn:
        driver = await conn.fetchrow("SELECT * FROM drivers WHERE national_id = $1", nid)
        if not driver:
            raise HTTPException(404, "Driver not found")

        # Background check
        outstanding = await conn.fetchval(
            "SELECT COALESCE(SUM(remaining_balance),0) FROM deductions WHERE national_id=$1 AND status='active'", nid
        )
        active_loans = await conn.fetchval(
            "SELECT COUNT(*) FROM deductions WHERE national_id=$1 AND deduction_type LIKE 'Loan%' AND status='active'", nid
        )
        # Current cycle earnings
        open_cycle = await conn.fetchrow(
            "SELECT id FROM payroll_cycles WHERE status NOT IN ('paid','cancelled') ORDER BY period_start DESC LIMIT 1"
        )
        cycle_earnings = Decimal("0")
        if open_cycle:
            earnings_row = await conn.fetchrow(
                """SELECT COALESCE(ppd_dld * ppd_price + cod_dld * cod_price + reverse_dld * reverse_price, 0) as earnings
                   FROM delivery_records WHERE national_id=$1 AND cycle_id=$2""",
                nid, open_cycle["id"]
            )
            if earnings_row:
                cycle_earnings = Decimal(str(earnings_row["earnings"]))

        amount     = Decimal(str(data["requested_amount"]))
        net_avail  = cycle_earnings - Decimal(str(outstanding))
        loan_ratio = float((amount / net_avail * 100) if net_avail > 0 else 999)

        flags = []
        if driver["pns_status"] != "approved": flags.append("PNS NOT APPROVED")
        if driver["employment_status"] != "active": flags.append(f"DRIVER STATUS: {driver['employment_status'].upper()}")
        if outstanding > 10000: flags.append(f"HIGH OUTSTANDING: {float(outstanding):,.2f} SAR")
        if active_loans >= 3: flags.append(f"MULTIPLE ACTIVE LOANS: {active_loans}")
        if loan_ratio > 100: flags.append("LOAN EXCEEDS ESTIMATED EARNINGS")
        elif loan_ratio > 80: flags.append("LOAN > 80% OF ESTIMATED EARNINGS")

        risk = "low"
        if flags: risk = "critical" if loan_ratio > 100 or driver["employment_status"] != "active" else "high" if loan_ratio > 80 or outstanding > 10000 else "medium"

        loan_data = {
            **data,
            "pns_status_at_request":   driver["pns_status"],
            "employment_status_at_req": driver["employment_status"],
            "cycle_earnings_to_date":  float(cycle_earnings),
            "pending_deductions_total": float(outstanding),
            "net_available":           float(net_avail),
            "loan_ratio":              loan_ratio,
            "previous_outstanding":    float(outstanding),
            "active_loans_count":      int(active_loans),
            "risk_level":              risk,
            "agent_flagged":           bool(flags),
            "flag_reasons":            json.dumps(flags),
        }
        cols = list(loan_data.keys())
        vals = [loan_data[k] for k in cols]
        lid  = await conn.fetchval(
            f"INSERT INTO loan_requests ({','.join(cols)}) VALUES ({','.join(f'${j+1}' for j in range(len(cols)))}) RETURNING id",
            *vals
        )

    return {"id": str(lid), "risk_level": risk, "flags": flags, "loan_ratio": loan_ratio}

# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
async def dashboard():
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """SELECT
               (SELECT COUNT(*) FROM drivers WHERE employment_status='active') AS active_drivers,
               (SELECT COUNT(*) FROM drivers WHERE employment_status='hold') AS held_drivers,
               (SELECT COUNT(*) FROM drivers WHERE pns_status='pending') AS pending_pns,
               (SELECT COUNT(*) FROM pn_requests WHERE expiry_date <= CURRENT_DATE+2 AND naafiz_status NOT IN ('approved','expired')) AS pns_expiring_48h,
               (SELECT COALESCE(SUM(remaining_balance),0) FROM deductions WHERE status='active') AS total_outstanding,
               (SELECT COUNT(*) FROM loan_requests WHERE final_status='pending') AS pending_loans,
               (SELECT COUNT(*) FROM risk_flags WHERE is_resolved=false AND severity='critical') AS critical_flags,
               (SELECT COUNT(*) FROM drivers WHERE vendor_code='SBY_DS03') AS sby_drivers"""
        )
        vendor_breakdown = await conn.fetch(
            """SELECT vendor_code, COUNT(*) as count
               FROM drivers WHERE employment_status='active' AND vendor_code IS NOT NULL
               GROUP BY vendor_code ORDER BY count DESC"""
        )
        recent_tx = await conn.fetch(
            """SELECT * FROM transactions ORDER BY created_at DESC LIMIT 10"""
        )
        alerts = await conn.fetch(
            "SELECT * FROM alerts WHERE is_read=false ORDER BY severity DESC, created_at DESC LIMIT 20"
        )
    return {
        "stats": dict(stats),
        "vendor_breakdown": [dict(r) for r in vendor_breakdown],
        "recent_transactions": [dict(r) for r in recent_tx],
        "alerts": [dict(r) for r in alerts],
    }

# ═══════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════

@app.get("/api/export/payroll/{cycle_id}")
async def export_payroll_csv(cycle_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM payroll_items WHERE cycle_id=$1 ORDER BY vendor_code, station_name, driver_name_ar",
            cycle_id
        )
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["NID","Name AR","Name EN","Vendor","Station","DA Type","DA Code",
                "PPD","COD","Reverse","Gross","Bank Fee","PN Fee","KDC Deductions",
                "Total Deductions","Net Payable","Status","IBAN","Bank"])
    for r in rows:
        kdc_total = sum(d["applied"] for d in (r["kdc_deductions"] or []))
        w.writerow([
            r["national_id"], r["driver_name_ar"], r["driver_name_en"],
            r["vendor_code"], r["station_name"], r["da_type"], r["da_code"],
            r["ppd_count"], r["cod_count"], r["reverse_count"],
            r["gross_salary"], r["bank_fee"], r["pn_fee"], kdc_total,
            r["total_deductions"], r["net_payable"],
            r["payment_status"], r["iban_number"], r["bank_name"]
        ])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll_{cycle_id}.csv"}
    )
