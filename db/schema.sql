-- QBO read-only cash-flow integration schema (PostgreSQL)
-- See docs/QBO_CASH_FLOW_INTEGRATION.md section 5 for the design rationale.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS qbo_connections (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    realm_id                    text NOT NULL UNIQUE,
    company_name                text,
    access_token_ciphertext     bytea NOT NULL,
    access_token_expires_at     timestamptz NOT NULL,
    refresh_token_ciphertext    bytea NOT NULL,
    refresh_token_expires_at    timestamptz NOT NULL,
    status                      text NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'needs_reauth', 'disconnected')),
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_balance_snapshots (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id     uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    qbo_account_id    text NOT NULL,
    account_name      text,
    current_balance   numeric(14,2) NOT NULL,
    snapshot_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bank_balance_snapshots_conn_snap
    ON bank_balance_snapshots (connection_id, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS invoice_snapshots (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id     uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    qbo_invoice_id    text NOT NULL,
    doc_number        text,
    customer_qbo_id   text,
    customer_name     text,
    txn_date          date,
    due_date          date,
    open_balance      numeric(14,2) NOT NULL,
    total_amt         numeric(14,2),
    snapshot_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (connection_id, qbo_invoice_id, snapshot_at)
);
CREATE INDEX IF NOT EXISTS idx_invoice_snapshots_conn_snap
    ON invoice_snapshots (connection_id, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS bill_snapshots (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id     uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    qbo_bill_id       text NOT NULL,
    doc_number        text,
    vendor_qbo_id     text,
    vendor_name       text,
    txn_date          date,
    due_date          date,
    open_balance      numeric(14,2) NOT NULL,
    total_amt         numeric(14,2),
    snapshot_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (connection_id, qbo_bill_id, snapshot_at)
);
CREATE INDEX IF NOT EXISTS idx_bill_snapshots_conn_snap
    ON bill_snapshots (connection_id, snapshot_at DESC);

-- Optional: historical payments, used to derive days-to-pay adjustments.
CREATE TABLE IF NOT EXISTS payment_history (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id                uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    direction                    text NOT NULL CHECK (direction IN ('inflow', 'outflow')),
    counterparty_qbo_id          text,
    counterparty_name            text,
    linked_invoice_or_bill_id    text,
    invoice_or_bill_date         date,
    payment_date                 date NOT NULL,
    amount                       numeric(14,2) NOT NULL,
    days_to_pay                  int,
    created_at                   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_history_conn_counterparty
    ON payment_history (connection_id, counterparty_qbo_id);

-- Optional: derived days-to-pay stats, refreshed daily from payment_history.
CREATE TABLE IF NOT EXISTS days_to_pay_stats (
    connection_id         uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    counterparty_qbo_id   text NOT NULL,
    counterparty_type     text NOT NULL CHECK (counterparty_type IN ('customer', 'vendor')),
    avg_days_to_pay       numeric(6,1),
    median_days_to_pay    numeric(6,1),
    sample_size           int NOT NULL DEFAULT 0,
    computed_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (connection_id, counterparty_qbo_id)
);

CREATE TABLE IF NOT EXISTS cash_flow_projections (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id         uuid NOT NULL REFERENCES qbo_connections(id) ON DELETE CASCADE,
    run_at                timestamptz NOT NULL,
    week_start_date       date NOT NULL,
    week_index            int NOT NULL CHECK (week_index BETWEEN 0 AND 12),
    starting_balance      numeric(14,2) NOT NULL,
    projected_inflows     numeric(14,2) NOT NULL,
    projected_outflows    numeric(14,2) NOT NULL,
    ending_balance        numeric(14,2) NOT NULL,
    UNIQUE (connection_id, run_at, week_index)
);
CREATE INDEX IF NOT EXISTS idx_cash_flow_projections_conn_run
    ON cash_flow_projections (connection_id, run_at DESC);

CREATE TABLE IF NOT EXISTS sync_audit_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id   uuid REFERENCES qbo_connections(id) ON DELETE CASCADE,
    action          text NOT NULL,
    status          text NOT NULL CHECK (status IN ('success', 'failure')),
    detail          text,
    occurred_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sync_audit_log_conn_time
    ON sync_audit_log (connection_id, occurred_at DESC);
