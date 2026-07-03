-- ============================================================
-- KDC DMFS — Driver Management & Financial Settlements System
-- PostgreSQL Schema v1.0
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- for fast text search

-- ============================================================
-- REFERENCE / LOOKUP TABLES
-- ============================================================

CREATE TABLE vendors (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code        VARCHAR(20) UNIQUE NOT NULL,  -- iMile, Ajex, Keeta, Naqel, J&T, Landmark, SBY_DS03
  name        VARCHAR(100) NOT NULL,
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO vendors (code, name) VALUES
  ('iMile',    'iMile Delivery'),
  ('Ajex',     'Ajex Express'),
  ('Keeta',    'Keeta'),
  ('Naqel',    'Naqel Express'),
  ('J&T',      'J&T Express'),
  ('Landmark', 'Landmark Logistics'),
  ('SBY_DS03', 'KDC SBY Dispatch Station 03');

CREATE TABLE stations (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name        VARCHAR(150) NOT NULL,
  city        VARCHAR(100),
  region      VARCHAR(100),
  vendor_code VARCHAR(20) REFERENCES vendors(code),
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE banks (
  id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name_en   VARCHAR(100) UNIQUE NOT NULL,
  name_ar   VARCHAR(100),
  swift     VARCHAR(20)
);

INSERT INTO banks (name_en, name_ar) VALUES
  ('Al Rajhi Bank',           'مصرف الراجحي'),
  ('Alinma Bank',             'مصرف الإنماء'),
  ('Bank Al Riyad',           'بنك الرياض'),
  ('Arab National Bank',      'البنك العربي الوطني'),
  ('Samba Financial Group',   'سامبا المالية'),
  ('Al Ahli Bank',            'البنك الأهلي التجاري'),
  ('Bank AlJazira',           'بنك الجزيرة'),
  ('Saudi Fransi',            'بنك الفرنسي السعودي'),
  ('Gulf International Bank', 'بنك الخليج الدولي'),
  ('Other',                   'أخرى');

-- ============================================================
-- CORE: DRIVERS
-- ============================================================

CREATE TABLE drivers (
  -- Identity
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  national_id           VARCHAR(10) UNIQUE NOT NULL,
  name_ar               VARCHAR(200),
  name_en               VARCHAR(200),
  mobile                VARCHAR(20),
  email                 VARCHAR(150),
  nationality           VARCHAR(50),

  -- Assignment
  vendor_code           VARCHAR(20) REFERENCES vendors(code),
  station_id            UUID REFERENCES stations(id),
  station_name          VARCHAR(150),  -- denormalized for speed
  city                  VARCHAR(100),

  -- DA / Contract
  da_type               VARCHAR(20) CHECK (da_type IN ('Per_Packet','Fixed_Salary','Salary_Owan')),
  da_code               VARCHAR(50),
  imile_id              VARCHAR(50),
  ajex_id               VARCHAR(50),
  keeta_id              VARCHAR(50),
  naqel_id              VARCHAR(50),
  jnt_id                VARCHAR(50),
  landmark_id           VARCHAR(50),
  amazon_id             VARCHAR(50),
  noon_id               VARCHAR(50),

  -- Employment
  employment_status     VARCHAR(20) DEFAULT 'active'
                        CHECK (employment_status IN ('active','hold','suspended','terminated','pending_pn')),
  hired_date            DATE,
  termination_date      DATE,
  termination_reason    TEXT,

  -- Banking
  bank_name             VARCHAR(100),
  iban_number           VARCHAR(34),
  account_owner_nid     VARCHAR(10),
  bank_status           VARCHAR(30),

  -- Naafiz / PN
  pns_status            VARCHAR(20) DEFAULT 'pending'
                        CHECK (pns_status IN ('approved','pending','rejected','expired')),
  pn_number             VARCHAR(30),
  pn_date               DATE,
  naafiz_fee            NUMERIC(10,2) DEFAULT 100,
  naafiz_received       NUMERIC(10,2) DEFAULT 0,
  naafiz_remaining      NUMERIC(10,2) DEFAULT 100,
  first_payment_processed BOOLEAN DEFAULT false,
  pn_fee_deducted       BOOLEAN DEFAULT false,

  -- Salary (for Fixed / Owan)
  basic_salary          NUMERIC(10,2),
  keeta_target          INTEGER,

  -- Meta
  supervisor_id         UUID,  -- FK to employees table
  notes                 TEXT,
  source                VARCHAR(20) DEFAULT 'sheets_import',  -- sheets_import, manual, form
  raw_sheet_row         JSONB,  -- store original row for audit
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookup
CREATE INDEX idx_drivers_nid        ON drivers(national_id);
CREATE INDEX idx_drivers_vendor     ON drivers(vendor_code);
CREATE INDEX idx_drivers_station    ON drivers(station_name);
CREATE INDEX idx_drivers_status     ON drivers(employment_status);
CREATE INDEX idx_drivers_pns        ON drivers(pns_status);
CREATE INDEX idx_drivers_name_ar    ON drivers USING gin(name_ar gin_trgm_ops);
CREATE INDEX idx_drivers_name_en    ON drivers USING gin(name_en gin_trgm_ops);
CREATE INDEX idx_drivers_da_code    ON drivers(da_code);
CREATE INDEX idx_drivers_imile      ON drivers(imile_id);
CREATE INDEX idx_drivers_ajex       ON drivers(ajex_id);

-- ============================================================
-- PRICING
-- ============================================================

CREATE TABLE station_pricing (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  vendor_code           VARCHAR(20) REFERENCES vendors(code),
  station_name          VARCHAR(150),
  ppd_price             NUMERIC(8,2) DEFAULT 0,   -- per prepaid delivery
  cod_price             NUMERIC(8,2) DEFAULT 0,   -- per COD delivery
  reverse_price         NUMERIC(8,2) DEFAULT 0,   -- per reverse pickup
  basic_salary_keeta    NUMERIC(10,2),             -- Keeta base salary
  target_orders_keeta   INTEGER,                   -- Keeta monthly target
  bonus_per_excess      NUMERIC(8,2) DEFAULT 10,  -- SAR per order above target
  penalty_per_deficit   NUMERIC(8,2) DEFAULT 10,  -- SAR per order below target
  effective_from        DATE DEFAULT CURRENT_DATE,
  is_active             BOOLEAN DEFAULT true,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(vendor_code, station_name, effective_from)
);

-- ============================================================
-- PN REQUESTS
-- ============================================================

CREATE TABLE pn_requests (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  national_id     VARCHAR(10) NOT NULL REFERENCES drivers(national_id) ON DELETE CASCADE,
  driver_name_ar  VARCHAR(200),
  driver_name_en  VARCHAR(200),
  station_name    VARCHAR(150),
  mobile          VARCHAR(20),
  naafiz_status   VARCHAR(20) DEFAULT 'pending'
                  CHECK (naafiz_status IN ('pending','submitted','approved','rejected','expired')),
  fee_amount      NUMERIC(10,2) DEFAULT 100,
  fee_status      VARCHAR(20) DEFAULT 'not_deducted'
                  CHECK (fee_status IN ('not_deducted','deducted','wasted')),
  requested_date  DATE DEFAULT CURRENT_DATE,
  expiry_date     DATE,
  days_remaining  INTEGER,
  approved_date   DATE,
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pn_nid     ON pn_requests(national_id);
CREATE INDEX idx_pn_status  ON pn_requests(naafiz_status);
CREATE INDEX idx_pn_expiry  ON pn_requests(expiry_date);

-- ============================================================
-- DEDUCTIONS
-- ============================================================

CREATE TABLE deductions (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  national_id       VARCHAR(10) NOT NULL REFERENCES drivers(national_id),
  driver_name       VARCHAR(200),
  deduction_type    VARCHAR(30) NOT NULL
                    CHECK (deduction_type IN (
                      'Loan','Loan_Petro_App','Loan_Future_App',
                      'Credit_Note','DFS_Amount','Violation',
                      'Pending_Naifaz','Advance_Salary',
                      'Carried_Down','Liability'
                    )),
  amount            NUMERIC(10,2) NOT NULL,        -- original principal
  remaining_balance NUMERIC(10,2) NOT NULL,        -- current outstanding
  installment_amount NUMERIC(10,2),               -- per-cycle deduction
  schedule_type     VARCHAR(20) DEFAULT 'per_cycle',
  priority          INTEGER NOT NULL,               -- lower = higher priority
  status            VARCHAR(20) DEFAULT 'active'
                    CHECK (status IN ('active','completed','on_hold','cancelled')),
  reference_number  VARCHAR(50),
  note              TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),
  completed_at      TIMESTAMPTZ
);

-- Priority constants (enforced in application layer too):
-- Violation:10, DFS_Amount:12, Liability:15, Pending_Naifaz:20
-- Loan_Petro_App:35, Loan_Future_App:40, Loan:40
-- Advance_Salary:50, Credit_Note:60, Carried_Down:60

CREATE INDEX idx_ded_nid    ON deductions(national_id);
CREATE INDEX idx_ded_status ON deductions(status);
CREATE INDEX idx_ded_type   ON deductions(deduction_type);

-- ============================================================
-- PAYROLL CYCLES
-- ============================================================

CREATE TABLE payroll_cycles (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  cycle_name      VARCHAR(100) NOT NULL,   -- "June 2026 — Cycle 1 (Jun 1–15)"
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  cycle_type      VARCHAR(20) DEFAULT 'biweekly'
                  CHECK (cycle_type IN ('biweekly','monthly')),
  vendor_code     VARCHAR(20),             -- null = all vendors
  status          VARCHAR(20) DEFAULT 'draft'
                  CHECK (status IN ('draft','processing','calculated','approved','paid')),
  total_drivers   INTEGER DEFAULT 0,
  total_gross     NUMERIC(12,2) DEFAULT 0,
  total_deductions NUMERIC(12,2) DEFAULT 0,
  total_net       NUMERIC(12,2) DEFAULT 0,
  total_held      NUMERIC(12,2) DEFAULT 0,
  finalized_at    TIMESTAMPTZ,
  finalized_by    VARCHAR(100),
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DELIVERY RECORDS (per driver per cycle)
-- ============================================================

CREATE TABLE delivery_records (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  national_id     VARCHAR(10) NOT NULL REFERENCES drivers(national_id),
  cycle_id        UUID NOT NULL REFERENCES payroll_cycles(id),
  driver_name     VARCHAR(200),
  vendor_code     VARCHAR(20),
  station_name    VARCHAR(150),
  da_type         VARCHAR(20),

  -- Delivery counts
  ppd_dld         INTEGER DEFAULT 0,   -- prepaid delivered
  cod_dld         INTEGER DEFAULT 0,   -- cash on delivery
  reverse_dld     INTEGER DEFAULT 0,   -- reverse pickup
  orders_delivered INTEGER DEFAULT 0,  -- total (Keeta)

  -- Prices applied (snapshot at time of calc)
  ppd_price       NUMERIC(8,2) DEFAULT 0,
  cod_price       NUMERIC(8,2) DEFAULT 0,
  reverse_price   NUMERIC(8,2) DEFAULT 0,

  data_source     VARCHAR(20) DEFAULT 'manual'
                  CHECK (data_source IN ('manual','google_sheets','imported')),
  is_verified     BOOLEAN DEFAULT false,
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(national_id, cycle_id)
);

CREATE INDEX idx_dr_nid     ON delivery_records(national_id);
CREATE INDEX idx_dr_cycle   ON delivery_records(cycle_id);

-- ============================================================
-- PAYROLL ITEMS (one per driver per cycle — final calc result)
-- ============================================================

CREATE TABLE payroll_items (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  cycle_id              UUID NOT NULL REFERENCES payroll_cycles(id),
  national_id           VARCHAR(10) NOT NULL REFERENCES drivers(national_id),
  driver_name_ar        VARCHAR(200),
  driver_name_en        VARCHAR(200),
  vendor_code           VARCHAR(20),
  station_name          VARCHAR(150),
  da_type               VARCHAR(20),
  da_code               VARCHAR(50),
  bank_name             VARCHAR(100),
  iban_number           VARCHAR(34),

  -- Earnings
  ppd_count             INTEGER DEFAULT 0,
  cod_count             INTEGER DEFAULT 0,
  reverse_count         INTEGER DEFAULT 0,
  orders_count          INTEGER DEFAULT 0,
  gross_salary          NUMERIC(10,2) NOT NULL,
  gross_breakdown       JSONB,    -- detailed calc breakdown

  -- Fixed deductions (outside 60% cap)
  bank_fee              NUMERIC(8,2) DEFAULT 8.50,
  pn_fee                NUMERIC(8,2) DEFAULT 0,
  is_first_payment      BOOLEAN DEFAULT false,

  -- KDC deductions (subject to 60% cap)
  kdc_deductions        JSONB,    -- [{type, priority, requested, applied, new_remaining}]
  total_kdc_deductions  NUMERIC(10,2) DEFAULT 0,

  -- Totals
  total_deductions      NUMERIC(10,2) DEFAULT 0,
  net_payable           NUMERIC(10,2) NOT NULL,
  incentive_amount      NUMERIC(10,2) DEFAULT 0,

  -- Cap tracking
  deduction_cap_applied BOOLEAN DEFAULT false,
  deduction_cap_pct     INTEGER DEFAULT 0,

  -- Status
  payment_status        VARCHAR(20) DEFAULT 'pending'
                        CHECK (payment_status IN ('pending','held','paid','cancelled')),
  hold_reason           TEXT,

  calculated_at         TIMESTAMPTZ DEFAULT NOW(),
  finalized_at          TIMESTAMPTZ,
  UNIQUE(cycle_id, national_id)
);

CREATE INDEX idx_pi_cycle   ON payroll_items(cycle_id);
CREATE INDEX idx_pi_nid     ON payroll_items(national_id);
CREATE INDEX idx_pi_status  ON payroll_items(payment_status);

-- ============================================================
-- LOAN REQUESTS
-- ============================================================

CREATE TABLE loan_requests (
  id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  national_id               VARCHAR(10) REFERENCES drivers(national_id),
  driver_name               VARCHAR(200),
  station_name              VARCHAR(150),
  vendor_code               VARCHAR(20),
  mobile                    VARCHAR(20),
  iban_number               VARCHAR(34),

  -- Request details
  requested_amount          NUMERIC(10,2) NOT NULL,
  request_category          VARCHAR(30)
                            CHECK (request_category IN (
                              'personal_loan','petrol_app','future_advance',
                              'advance_salary','emergency','other'
                            )),
  reason                    TEXT,
  requested_by              VARCHAR(100),  -- supervisor name/email
  requested_at              TIMESTAMPTZ DEFAULT NOW(),

  -- Background check (auto-computed)
  pns_status_at_request     VARCHAR(20),
  employment_status_at_req  VARCHAR(20),
  cycle_earnings_to_date    NUMERIC(10,2) DEFAULT 0,
  pending_deductions_total  NUMERIC(10,2) DEFAULT 0,
  net_available             NUMERIC(10,2) DEFAULT 0,
  loan_ratio                NUMERIC(5,2) DEFAULT 0,  -- loan/net as %
  previous_outstanding      NUMERIC(10,2) DEFAULT 0,
  active_loans_count        INTEGER DEFAULT 0,
  risk_level                VARCHAR(10)
                            CHECK (risk_level IN ('low','medium','high','critical')),
  agent_flagged             BOOLEAN DEFAULT false,
  flag_reasons              JSONB,  -- ["PNS NOT APPROVED","LOAN > 80% EARNINGS"]

  -- Approval pipeline
  agent_status              VARCHAR(20) DEFAULT 'pending_review'
                            CHECK (agent_status IN ('pending_review','reviewed','escalated')),
  agent_reviewed_at         TIMESTAMPTZ,
  agent_recommendation      VARCHAR(20)
                            CHECK (agent_recommendation IN ('approve','reject','escalate')),

  supervisor_status         VARCHAR(20) DEFAULT 'pending',
  supervisor_reviewed_by    VARCHAR(100),
  supervisor_reviewed_at    TIMESTAMPTZ,
  supervisor_notes          TEXT,

  owner_notified_at         TIMESTAMPTZ,
  owner_confirmed           BOOLEAN,
  owner_confirmed_at        TIMESTAMPTZ,

  final_status              VARCHAR(20) DEFAULT 'pending'
                            CHECK (final_status IN ('pending','approved','rejected','cancelled')),
  rejection_reason          TEXT,
  approved_amount           NUMERIC(10,2),
  approved_at               TIMESTAMPTZ,

  -- Disbursement
  disbursed                 BOOLEAN DEFAULT false,
  disbursed_at              TIMESTAMPTZ,
  disbursed_by              VARCHAR(100),

  created_at                TIMESTAMPTZ DEFAULT NOW(),
  updated_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lr_nid     ON loan_requests(national_id);
CREATE INDEX idx_lr_status  ON loan_requests(final_status);
CREATE INDEX idx_lr_risk    ON loan_requests(risk_level);

-- ============================================================
-- TRANSACTIONS (complete financial ledger)
-- ============================================================

CREATE TABLE transactions (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  transaction_date  DATE NOT NULL DEFAULT CURRENT_DATE,
  direction         VARCHAR(10) NOT NULL CHECK (direction IN ('money_in','money_out')),
  amount            NUMERIC(12,2) NOT NULL,
  category          VARCHAR(50) NOT NULL,
  description       TEXT,

  -- Links
  national_id       VARCHAR(10),
  driver_name       VARCHAR(200),
  cycle_id          UUID REFERENCES payroll_cycles(id),
  loan_request_id   UUID REFERENCES loan_requests(id),
  vendor_code       VARCHAR(20),
  station_name      VARCHAR(150),

  -- Payment details
  payment_method    VARCHAR(30)
                    CHECK (payment_method IN ('bank_transfer','cash','cheque','system_deduction','internal')),
  reference_number  VARCHAR(100),
  status            VARCHAR(20) DEFAULT 'completed'
                    CHECK (status IN ('pending','completed','reversed','cancelled')),

  notes             TEXT,
  created_by        VARCHAR(100),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tx_date     ON transactions(transaction_date);
CREATE INDEX idx_tx_nid      ON transactions(national_id);
CREATE INDEX idx_tx_category ON transactions(category);
CREATE INDEX idx_tx_direction ON transactions(direction);

-- ============================================================
-- RISK FLAGS
-- ============================================================

CREATE TABLE risk_flags (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  flag_category   VARCHAR(50) NOT NULL,
  flag_type       VARCHAR(30) NOT NULL
                  CHECK (flag_type IN ('financial_risk','operational_risk','compliance_risk','payroll_risk')),
  severity        VARCHAR(10) NOT NULL
                  CHECK (severity IN ('critical','high','medium','low')),
  title           VARCHAR(200) NOT NULL,
  description     TEXT,
  national_id     VARCHAR(10),
  driver_name     VARCHAR(200),
  station_name    VARCHAR(150),
  vendor_code     VARCHAR(20),
  amount_at_risk  NUMERIC(12,2) DEFAULT 0,
  risk_score      INTEGER DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
  is_resolved     BOOLEAN DEFAULT false,
  resolved_at     TIMESTAMPTZ,
  resolved_by     VARCHAR(100),
  resolution_notes TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rf_severity  ON risk_flags(severity);
CREATE INDEX idx_rf_resolved  ON risk_flags(is_resolved);
CREATE INDEX idx_rf_nid       ON risk_flags(national_id);

-- ============================================================
-- USERS / AUTH
-- ============================================================

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email         VARCHAR(150) UNIQUE NOT NULL,
  name          VARCHAR(100),
  role          VARCHAR(20) DEFAULT 'viewer'
                CHECK (role IN ('owner','admin','supervisor','viewer')),
  vendor_code   VARCHAR(20),   -- if supervisor, which vendor they manage
  station_name  VARCHAR(150),  -- if supervisor, which station
  is_active     BOOLEAN DEFAULT true,
  last_login    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Default owner
INSERT INTO users (email, name, role) VALUES ('jasirmanzoor2@gmail.com', 'Abdullah', 'owner');

-- ============================================================
-- ALERTS
-- ============================================================

CREATE TABLE alerts (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  alert_type  VARCHAR(50),
  severity    VARCHAR(10) CHECK (severity IN ('critical','warning','info')),
  title       VARCHAR(200),
  message     TEXT,
  national_id VARCHAR(10),
  related_id  UUID,
  is_read     BOOLEAN DEFAULT false,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- SHEETS SYNC LOG
-- ============================================================

CREATE TABLE sheets_sync_log (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  sync_type       VARCHAR(30),   -- 'drivers','pn','loans','delivery','full'
  sheet_name      VARCHAR(100),
  status          VARCHAR(20)    CHECK (status IN ('running','completed','failed','partial')),
  rows_read       INTEGER DEFAULT 0,
  records_created INTEGER DEFAULT 0,
  records_updated INTEGER DEFAULT 0,
  records_skipped INTEGER DEFAULT 0,
  errors_count    INTEGER DEFAULT 0,
  error_log       JSONB,
  started_at      TIMESTAMPTZ DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  triggered_by    VARCHAR(100)
);

-- ============================================================
-- UPDATED_AT TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_drivers_updated      BEFORE UPDATE ON drivers         FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_deductions_updated   BEFORE UPDATE ON deductions       FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_pn_updated           BEFORE UPDATE ON pn_requests      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_cycles_updated       BEFORE UPDATE ON payroll_cycles   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_lr_updated           BEFORE UPDATE ON loan_requests    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_dr_updated           BEFORE UPDATE ON delivery_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
