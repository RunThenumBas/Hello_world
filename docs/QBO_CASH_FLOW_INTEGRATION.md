# QuickBooks Online (QBO) Read-Only Integration — 13-Week Cash Flow Projection

Stack decisions for this build: **Node.js + Express**, **single QBO company (single-tenant)**, **PostgreSQL**, tokens encrypted at rest with an **app-level AES-256-GCM key from env**. Everything below (and the code in `src/`) is built against those choices. Where multi-tenant matters, it's called out so you can extend later.

Scope is strictly **read-only** — this app never calls a QBO write/update/delete endpoint. Cash-basis only.

---

## 1. Intuit Developer App Setup

1. **Create an Intuit Developer account**: go to `developer.intuit.com` → sign in with (or create) an Intuit account.
2. **Create an app**: Dashboard → *Create an app* → choose **QuickBooks Online and Payments** (you only need QBO Accounting API; you can leave Payments unchecked if offered as a separate product).
3. **Select scopes at app-creation time**: pick **Accounting** (this is the scope family that exposes Customers, Vendors, Invoices, Bills, Accounts, Reports, Payments — everything you need). You do **not** need Payroll, Payments (money movement), or Time Tracking scopes.
4. **Get your credentials** (Dashboard → your app → *Keys & OAuth*):
   - **Client ID** — public-ish identifier for your app, sent in the authorization URL.
   - **Client Secret** — confidential, used only in server-to-server calls (code-for-token exchange, refresh). Never expose to a browser/mobile client.
   - Intuit gives you **separate Development and Production keys**. Development keys only work against **Sandbox companies** (fake QBO companies Intuit provisions for testing — Dashboard → *Sandbox*). You must apply for **Production keys** (a short app review, mostly about scopes/permissions requested matching what your app actually does) before you can connect real customer QBO companies.
5. **Redirect URI (a.k.a. callback URL)**: this is the URL on *your* server that Intuit's authorization server redirects the user's browser back to after they approve (or deny) access, with a one-time `code` in the query string. It must:
   - Be **HTTPS** in production (Intuit allows `http://localhost:...` for local dev only).
   - Be registered **exactly** (scheme, host, port, path — no wildcards) in the app's *Keys & OAuth* page under **Redirect URIs**. A mismatch is the #1 cause of `redirect_uri_mismatch` errors.
   - Example for this project: `https://yourapp.example.com/callback` (local dev: `http://localhost:3000/callback`).
6. **Note the two environments**: `Sandbox` (fake data, use Development keys) and `Production` (real company data, use Production keys). The OAuth base URLs are the same for both — what differs is the API base URL you call (`sandbox-quickbooks.api.intuit.com` vs `quickbooks.api.intuit.com`) and which Client ID/Secret pair you use.

What you end up with: `CLIENT_ID`, `CLIENT_SECRET`, one or more registered `REDIRECT_URI`s, and a sandbox company to test against before going to production.

---

## 2. OAuth 2.0 Flow (Authorization Code Grant, server-side)

QBO uses standard OAuth 2.0 Authorization Code flow plus a QBO-specific concept: the **`realmId`** (a.k.a. Company ID) — the identifier of the specific QBO company the user connected. Every API call needs it; it comes back on the callback.

### 2.1 Step 1 — Build the authorization URL (`/connect`)

Redirect the user's browser to:

```
https://appcenter.intuit.com/connect/oauth2?
  client_id={CLIENT_ID}
  &redirect_uri={REDIRECT_URI}   (URL-encoded, must exactly match a registered URI)
  &response_type=code
  &scope=com.intuit.quickbooks.accounting
  &state={RANDOM_CSRF_TOKEN}
```

- `state` — generate a random, unguessable value per auth attempt (e.g. `crypto.randomBytes(16).toString('hex')`), store it server-side (session or short-lived DB row), and verify it matches on callback. This is your CSRF protection — reject the callback if it doesn't match.
- The user logs into QBO (if not already) and sees a consent screen listing the data your app can read, then approves or denies.

### 2.2 Step 2 — Handle the callback (`/callback`)

Intuit redirects to your `REDIRECT_URI` with query params:

```
GET /callback?code=AB1234...&state=...&realmId=193514...&error=...
```

Server-side, you must:
1. If `error` is present (user denied, or another failure) → show a friendly failure page, do not proceed.
2. Verify `state` matches what you stored for this session → if not, reject (401) — possible CSRF.
3. Extract `code` and `realmId`.
4. Exchange `code` for tokens (Step 3, below) **immediately** — the authorization code is single-use and expires in ~10 minutes.
5. Persist the resulting tokens + `realmId`, associated with your internal user/company record (encrypted — see §6).
6. Redirect the browser to a "connected!" page in your app (don't leave the QBO code/state in the URL bar longer than necessary).

### 2.3 Step 3 — Exchange authorization code for tokens

`POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`

Headers: `Authorization: Basic base64(CLIENT_ID:CLIENT_SECRET)`, `Content-Type: application/x-www-form-urlencoded`, `Accept: application/json`

Body: `grant_type=authorization_code&code={code}&redirect_uri={REDIRECT_URI}`

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "AB1...",
  "token_type": "bearer",
  "expires_in": 3600,
  "x_refresh_token_expires_in": 8726400
}
```

- **Access token**: valid **1 hour**. Sent as `Authorization: Bearer {access_token}` on every Accounting API call.
- **Refresh token**: valid **100 days** from issuance, and importantly **rotates on every use** — each refresh call returns a *new* refresh token that replaces the old one, and the old one is invalidated. You must overwrite your stored refresh token every time you refresh, or you will eventually get locked out.
- If the refresh token expires (100 days with no successful refresh, or the user revokes access in their Intuit account, or disconnects the app), the user must go through `/connect` again. Detect this (a 401/`invalid_grant` on refresh) and mark the connection as needing re-auth rather than silently failing.

### 2.4 Step 4 — Refresh the access token

`POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`

Same headers as above. Body: `grant_type=refresh_token&refresh_token={current_refresh_token}`

Response shape is identical to the code exchange response — store the new `access_token`, its expiry, **and the new `refresh_token`**.

**Recommended pattern**: don't wait for a 401 from an API call to refresh. Before each API call (or each sync run), check if `access_token_expires_at` is within e.g. 2 minutes of now; if so, refresh first. Keep a fallback: if an API call still returns 401, refresh once and retry the call once, then give up and flag the connection.

---

## 3. Minimum Required Scopes (least privilege)

QBO's OAuth scope model is coarse — there's one scope that covers the whole Accounting API surface:

- **`com.intuit.quickbooks.accounting`** — required. Grants read (and write, which we simply never use) access to Customers, Vendors, Invoices, Bills, Bank/Accounts, Payments, Reports, etc.

Do **not** request (and your Intuit app should not be configured with):
- `com.intuit.quickbooks.payment` — QBO Payments (money movement / charging cards) — unrelated to reading cash flow data.
- Payroll scopes (`com.intuit.quickbooks.payroll*`) — not needed; we don't read payroll, and pulling it would create unnecessary PII/compliance exposure.
- `openid` / `profile` / `email` / `phone` / `address` — these are for "Sign in with Intuit" (getting the QBO *user's* identity). Skip unless you specifically need SSO; they add personal data you don't need to collect.

Because QBO has no finer-grained scope than "accounting", least-privilege enforcement for this app happens at two other layers instead:
1. **API-level**: only ever call the read (`GET`) endpoints listed in §4. Never call the corresponding `POST`/write endpoints — enforce this by only implementing GET wrapper functions in `qboClient.js` (see code) and not implementing any write methods at all.
2. **Data-level**: only select/store the fields listed in §4/§5 from each response; don't persist entire raw payloads if they contain PII you don't need (see §8).

---

## 4. QBO Endpoints / Reports to Pull

Base URL: `https://quickbooks.api.intuit.com/v3/company/{realmId}/...` (sandbox: `https://sandbox-quickbooks.api.intuit.com/v3/company/{realmId}/...`)
Auth: `Authorization: Bearer {access_token}`, `Accept: application/json`

| # | Call | Purpose | Key fields to keep | Refresh frequency |
|---|------|---------|---------------------|--------------------|
| 1 | `GET /v3/company/{realmId}/query?query=SELECT * FROM Account WHERE AccountType IN ('Bank')` | Bank account balances = cash on hand | `Id`, `Name`, `AccountSubType`, `CurrentBalance`, `CurrentBalanceWithSubAccounts`, `Active` | Every sync (30–60 min) — this is your "as of today" starting balance |
| 2 | `GET /v3/company/{realmId}/query?query=SELECT * FROM Invoice WHERE Balance > '0'` (paginated with `STARTPOSITION`/`MAXRESULTS`) | Open invoices → expected cash inflows | `Id`, `DocNumber`, `TxnDate`, `DueDate`, `Balance`, `TotalAmt`, `CustomerRef.value`, `CustomerRef.name` | Every sync (30–60 min) |
| 3 | `GET /v3/company/{realmId}/query?query=SELECT * FROM Bill WHERE Balance > '0'` (paginated) | Unpaid bills → expected cash outflows | `Id`, `DocNumber`, `TxnDate`, `DueDate`, `Balance`, `TotalAmt`, `VendorRef.value`, `VendorRef.name` | Every sync (30–60 min) |
| 4 (optional) | `GET /v3/company/{realmId}/query?query=SELECT * FROM Payment WHERE TxnDate >= '{today-365d}'` (paginated) | Historical customer payments → derive actual days-to-pay per customer | `Id`, `TxnDate`, `CustomerRef.value`, `TotalAmt`, `Line[].LinkedTxn[]` (to map back to the invoice, for invoice-date vs payment-date delta) | Daily (this data changes slowly; no need to hammer it every 30 min) |
| 5 (optional) | `GET /v3/company/{realmId}/query?query=SELECT * FROM BillPayment WHERE TxnDate >= '{today-365d}'` (paginated) | Historical bill payments → derive actual days-to-pay per vendor | `Id`, `TxnDate`, `VendorRef.value`, `TotalAmt`, `Line[].LinkedTxn[]` | Daily |
| 6 | `GET /v3/company/{realmId}/companyinfo/{realmId}` | Company metadata (name, fiscal year, base currency) — not cash-flow data itself, but needed once to label reports and confirm the connection is alive | `CompanyName`, `Country`, `FiscalYearStartMonth` | Once at connect time; re-check daily as a lightweight liveness probe |

Notes:
- Prefer the **Query endpoint** (`/query?query=SELECT ...`) with explicit `WHERE Balance > '0'` filters over pulling *all* invoices/bills — it's both more efficient and naturally scopes you to only the open items you need (least-privilege on data, not just scope).
- Paginate with `STARTPOSITION`/`MAXRESULTS` (QBO caps at 1000 rows per page); loop until a page returns fewer than `MAXRESULTS` rows.
- An alternative to raw `Invoice`/`Bill` queries is the **`AgedReceivables`**/**`AgedPayables`** report endpoints (`/v3/company/{realmId}/reports/AgedReceivableDetail`) — they're convenient for display but return a denormalized report structure that's more annoying to parse into rows than the entity Query API. Recommendation: use the entity `Query` endpoints (#1–#3) as the source of truth for the projection engine; use report endpoints only if you later want a "does this match what QBO's own AR/AP aging report shows" reconciliation check.
- Respect QBO's rate limits (roughly 500 requests/min per realm, 10 concurrent requests per realm) — the sync job in §6 pulls sequentially per entity type, which stays well under this for a single company.

---

## 5. Data Schema (PostgreSQL)

Design principles: every pulled row is a **timestamped snapshot** (never overwritten in place) so you can see history and debug "why did the projection change"; only PII actually needed is stored; tokens live in their own tightly-scoped table. Full DDL is in [`db/schema.sql`](../db/schema.sql) — summarized here:

### `qbo_connections`
One row per connected QBO company (single-tenant build = effectively one active row).
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `realm_id` | text unique | QBO company ID |
| `company_name` | text | from CompanyInfo |
| `access_token_ciphertext` | bytea | AES-256-GCM encrypted |
| `access_token_expires_at` | timestamptz | |
| `refresh_token_ciphertext` | bytea | AES-256-GCM encrypted, **overwritten on every refresh** |
| `refresh_token_expires_at` | timestamptz | |
| `status` | text | `active` / `needs_reauth` / `disconnected` |
| `created_at`, `updated_at` | timestamptz | |

### `bank_balance_snapshots`
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `connection_id` | uuid FK → qbo_connections | |
| `qbo_account_id` | text | QBO `Account.Id` |
| `account_name` | text | |
| `current_balance` | numeric(14,2) | |
| `snapshot_at` | timestamptz | when we pulled it |

### `invoice_snapshots` (open invoices — inflows)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `connection_id` | uuid FK | |
| `qbo_invoice_id` | text | |
| `doc_number` | text | |
| `customer_qbo_id` | text | |
| `customer_name` | text | |
| `txn_date` | date | invoice date |
| `due_date` | date | |
| `open_balance` | numeric(14,2) | |
| `total_amt` | numeric(14,2) | |
| `snapshot_at` | timestamptz | |
`UNIQUE (connection_id, qbo_invoice_id, snapshot_at)` — snapshot table, not upsert-in-place, so you can trend "did this invoice's balance change."

### `bill_snapshots` (unpaid bills — outflows)
Same shape as `invoice_snapshots`, with `vendor_qbo_id`/`vendor_name` instead of customer, table name `bill_snapshots`, column `qbo_bill_id`.

### `payment_history` (optional, for days-to-pay)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `connection_id` | uuid FK | |
| `direction` | text | `'inflow'` (Payment) or `'outflow'` (BillPayment) |
| `counterparty_qbo_id` | text | customer or vendor id |
| `counterparty_name` | text | |
| `linked_invoice_or_bill_id` | text nullable | from `LinkedTxn` |
| `invoice_or_bill_date` | date nullable | |
| `payment_date` | date | |
| `amount` | numeric(14,2) | |
| `days_to_pay` | int nullable | `payment_date - invoice_or_bill_date`, computed on insert |

### `days_to_pay_stats` (derived, refreshed daily)
| column | type | notes |
|---|---|---|
| `connection_id` | uuid FK | |
| `counterparty_qbo_id` | text | |
| `counterparty_type` | text | `customer` / `vendor` |
| `avg_days_to_pay` | numeric(6,1) | trailing 12 months |
| `median_days_to_pay` | numeric(6,1) | |
| `sample_size` | int | |
| `computed_at` | timestamptz | |
`PRIMARY KEY (connection_id, counterparty_qbo_id)`

### `cash_flow_projections` (output of the algorithm, one row per week bucket per run)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `connection_id` | uuid FK | |
| `run_at` | timestamptz | when this projection was generated |
| `week_start_date` | date | Monday of the bucket |
| `week_index` | int | 0–12 |
| `starting_balance` | numeric(14,2) | running balance entering the week |
| `projected_inflows` | numeric(14,2) | |
| `projected_outflows` | numeric(14,2) | |
| `ending_balance` | numeric(14,2) | |
`UNIQUE (connection_id, run_at, week_index)`

### `sync_audit_log` (§8 — audit trail)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `connection_id` | uuid FK | |
| `action` | text | e.g. `token_refresh`, `pull_invoices`, `pull_bills`, `pull_balances`, `projection_run` |
| `status` | text | `success` / `failure` |
| `detail` | text | error message or row counts — **never** log token values or full response bodies |
| `occurred_at` | timestamptz | |

---

## 6. Starter Code Structure (Node.js + Express)

Full runnable skeleton lives under `src/` and `db/` in this repo:

```
src/
  server.js            # Express app bootstrap, mounts routes, starts scheduler
  config.js            # loads/validates env vars
  db/
    pool.js             # pg Pool
  services/
    crypto.js           # AES-256-GCM encrypt/decrypt helpers for token storage
    tokenStore.js        # save/load/refresh tokens against qbo_connections
    qboClient.js         # thin fetch wrapper: query(), get() — GET-only, no write methods exist
    sync.js              # pullBankBalances(), pullOpenInvoices(), pullOpenBills(), pullPaymentHistory()
    projection.js        # buildThirteenWeekProjection()
    auditLog.js          # writeAudit()
  routes/
    auth.js              # GET /connect, GET /callback, GET /disconnect
    dashboard.js          # GET /api/projection (reads latest cash_flow_projections)
  jobs/
    scheduler.js          # node-cron job, every 30–60 min, calls sync.js then projection.js
db/
  schema.sql             # DDL for all tables in §5
.env.example
package.json
```

### 6.1 `/connect` route (outline)

```js
// src/routes/auth.js
router.get('/connect', (req, res) => {
  const state = crypto.randomBytes(16).toString('hex');
  req.session.oauthState = state; // or a short-lived DB row keyed by a signed cookie
  const authUrl = oauthClient.authorizeUri({
    scope: ['com.intuit.quickbooks.accounting'],
    state,
  });
  res.redirect(authUrl);
});
```

### 6.2 `/callback` route (outline)

```js
router.get('/callback', async (req, res) => {
  const { code, state, realmId, error } = req.query;
  if (error) return res.status(400).send('Authorization denied.');
  if (!state || state !== req.session.oauthState) return res.status(401).send('Invalid state.');

  const tokenResponse = await oauthClient.createToken(req.url); // exchanges code for tokens
  await tokenStore.saveNewConnection({
    realmId,
    accessToken: tokenResponse.access_token,
    accessTokenExpiresIn: tokenResponse.expires_in,
    refreshToken: tokenResponse.refresh_token,
    refreshTokenExpiresIn: tokenResponse.x_refresh_token_expires_in,
  });
  await auditLog.write({ action: 'connect', status: 'success', realmId });
  res.redirect('/connected');
});
```

### 6.3 Token storage — encrypted at rest (outline)

```js
// src/services/crypto.js
const KEY = Buffer.from(process.env.TOKEN_ENCRYPTION_KEY, 'base64'); // 32 bytes

function encrypt(plaintext) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', KEY, iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]); // iv(12) || tag(16) || ciphertext
}

function decrypt(blob) {
  const iv = blob.subarray(0, 12);
  const tag = blob.subarray(12, 28);
  const ciphertext = blob.subarray(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', KEY, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}
```

`tokenStore.js` calls `encrypt()`/`decrypt()` around every read/write of `access_token_ciphertext`/`refresh_token_ciphertext` — **plaintext tokens never touch the database or logs.**

### 6.4 Scheduled sync job (every 30–60 min)

```js
// src/jobs/scheduler.js
const cron = require('node-cron');
cron.schedule('*/30 * * * *', async () => {
  const connection = await tokenStore.getActiveConnection();
  if (!connection) return;
  await tokenStore.ensureFreshAccessToken(connection); // refreshes if within 2 min of expiry
  await sync.pullBankBalances(connection);
  await sync.pullOpenInvoices(connection);
  await sync.pullOpenBills(connection);
  await projection.buildThirteenWeekProjection(connection);
});
// separate daily job for payment history / days-to-pay stats (cheaper cadence, larger pull)
cron.schedule('0 3 * * *', async () => {
  const connection = await tokenStore.getActiveConnection();
  if (!connection) return;
  await sync.pullPaymentHistory(connection);
  await sync.recomputeDaysToPayStats(connection);
});
```

### 6.5 Pull functions (outline)

```js
// src/services/sync.js
async function pullOpenInvoices(connection) {
  const rows = await qboClient.queryAll(connection, "SELECT * FROM Invoice WHERE Balance > '0'");
  const snapshotAt = new Date();
  await db.transaction(async (trx) => {
    for (const inv of rows) {
      await trx('invoice_snapshots').insert({
        connection_id: connection.id,
        qbo_invoice_id: inv.Id,
        doc_number: inv.DocNumber,
        customer_qbo_id: inv.CustomerRef?.value,
        customer_name: inv.CustomerRef?.name,
        txn_date: inv.TxnDate,
        due_date: inv.DueDate,
        open_balance: inv.Balance,
        total_amt: inv.TotalAmt,
        snapshot_at: snapshotAt,
      });
    }
  });
  await auditLog.write({ action: 'pull_invoices', status: 'success', detail: `${rows.length} rows` });
}
// pullOpenBills and pullBankBalances follow the same shape against Bill / Account.
```

`qboClient.js` exposes only `get(connection, path)` and `queryAll(connection, soqlQuery)` (auto-paginating GET wrappers) — there is intentionally no `post`/`update`/`delete` method in the module, so a write call is a compile-time-obvious addition, not an accidental one-liner.

---

## 7. Cash-Basis 13-Week Projection Algorithm (outline)

Inputs (from the latest snapshot as of `run_at`):
- `starting_cash` = sum of `current_balance` across all rows in the latest `bank_balance_snapshots` snapshot.
- `open_invoices[]` = latest snapshot rows from `invoice_snapshots` (each: amount, due_date, customer).
- `open_bills[]` = latest snapshot rows from `bill_snapshots` (each: amount, due_date, vendor).
- optional `days_to_pay_stats` keyed by customer/vendor.

Algorithm:

```
function buildThirteenWeekProjection(connection):
    today = current date
    week_buckets = [ (today + 7*i, today + 7*(i+1) - 1 day) for i in 0..12 ]   # 13 weekly buckets, Mon-Sun

    starting_cash = latest bank_balance_snapshots total for connection

    open_invoices = latest invoice_snapshots for connection
    open_bills    = latest bill_snapshots for connection

    for each invoice in open_invoices:
        expected_date = invoice.due_date
        if USE_DAYS_TO_PAY_ADJUSTMENT and stats exist for invoice.customer_qbo_id:
            # shift expectation from due_date toward "when this customer actually tends to pay"
            # anchor off invoice.txn_date (invoice date), not due_date, since days-to-pay is
            # measured invoice_date -> payment_date historically
            expected_date = invoice.txn_date + avg_days_to_pay(invoice.customer_qbo_id)
            expected_date = max(expected_date, today)   # never project a "payment" in the past
        invoice.expected_date = expected_date

    for each bill in open_bills:
        expected_date = bill.due_date
        if USE_DAYS_TO_PAY_ADJUSTMENT and stats exist for bill.vendor_qbo_id:
            expected_date = bill.txn_date + avg_days_to_pay(bill.vendor_qbo_id)
            expected_date = max(expected_date, today)
        bill.expected_date = expected_date

    # Anything already overdue (expected_date < today) is bucketed into week 0 —
    # "expected to be collected/paid immediately" is the simplest, most conservative
    # cash-basis treatment; don't drop it from the projection.
    for invoice in open_invoices:
        invoice.bucket_week = clamp(week_index_for(invoice.expected_date, week_buckets), min=0, max=12)
    for bill in open_bills:
        bill.bucket_week = clamp(week_index_for(bill.expected_date, week_buckets), min=0, max=12)

    running_balance = starting_cash
    results = []
    for week_index in 0..12:
        inflow  = sum(invoice.open_balance for invoice in open_invoices if invoice.bucket_week == week_index)
        outflow = sum(bill.open_balance for bill in open_bills if bill.bucket_week == week_index)
        week_start = starting_balance = running_balance
        running_balance = running_balance + inflow - outflow
        results.append({
            week_index, week_start_date: week_buckets[week_index][0],
            starting_balance: week_start, projected_inflows: inflow,
            projected_outflows: outflow, ending_balance: running_balance,
        })

    persist results to cash_flow_projections with run_at = now()
    return results
```

Notes:
- This is **cash-basis by construction**: it only recognizes cash when it's expected to actually move (invoice due/expected-payment date, bill due/expected-payment date), never on the accrual transaction date.
- Anything invoiced/billed with **no due date** in QBO should fall back to `txn_date + a configurable default term (e.g. Net 30)` rather than being silently excluded — surface this fallback in the row so users can see it's an estimate.
- Days-to-pay adjustment (`days_to_pay_stats`, computed from `payment_history`) is **additive/optional** — ship the naive due-date version first (this is what you told me to prioritize), gate the adjustment behind a flag once `payment_history` is populated (needs the daily historical pull from §4 row 4–5) and you've validated `avg_days_to_pay` looks sane (e.g. `sample_size >= 3`).
- Re-running the projection is idempotent per `run_at` — each scheduled sync produces a fresh, fully-replaced 13-row set; don't try to patch old rows.

---

## 8. Security Checklist

**Secrets handling**
- `CLIENT_SECRET` and `TOKEN_ENCRYPTION_KEY` live only in environment variables (`.env`, excluded via `.gitignore`; in real deployment, your platform's secret manager — e.g. host env vars injected at deploy time). Never commit `.env`.
- `TOKEN_ENCRYPTION_KEY` is a 32-byte value, base64-encoded, generated once via `openssl rand -base64 32` and stored outside the repo. Document a key-rotation procedure (decrypt all rows with old key, re-encrypt with new key, in a maintenance script) even if you don't build it on day one.
- Access + refresh tokens are **encrypted at rest** (§6.3) — the database itself, if dumped or leaked, does not expose usable QBO credentials.
- Never log tokens, `Authorization` headers, or full QBO API response bodies. `auditLog.write()` only ever takes a short `detail` string (row counts, error class), never raw payloads.

**Least privilege**
- Single OAuth scope (`com.intuit.quickbooks.accounting`) — see §3 for why nothing narrower exists, and why enforcement instead happens at the code level (GET-only client) and data level (only persist the columns in §5).
- Database role used by the app: `GRANT SELECT, INSERT, UPDATE ON <the tables it needs>` — no `DELETE`, no `DROP`, no access to other schemas if this DB is shared with other apps.
- If you ever add a human-facing admin UI, put it behind its own auth (separate from the QBO OAuth flow) and make sure it can't display decrypted tokens even to admins — expose connection *status* (`active`/`needs_reauth`), not token values.

**Audit logs**
- Every OAuth event (connect, refresh, disconnect, refresh failure) and every sync action writes a row to `sync_audit_log` (§5) — status + row counts + timestamp, no sensitive payloads.
- Alert (email/Slack webhook, outside this doc's scope) on `status = 'failure'` rows, especially repeated refresh failures — that's your signal the connection needs re-auth.

**Avoiding sensitive-field leakage**
- The QBO `Customer`/`Vendor`/`Invoice`/`Bill` objects carry far more than you need — billing addresses, phone numbers, email, sometimes linked bank-transfer details on `Payment`/`BillPayment` objects. §5's schema **only has columns for what §4 lists**; don't add an `raw_payload jsonb` catch-all column unless you have a specific reason, since that's exactly how addresses/PII end up persisted "by accident."
- Payroll is out of scope entirely — don't request payroll scopes, don't call payroll endpoints (see §3).
- If you build any export/report feature on top of this, review what fields it surfaces before shipping — `customer_name`/`vendor_name` are fine for a cash flow view; don't join back to full QBO customer records for addresses/contact info unless a real feature needs it.

**Tenant/company data isolation** (matters even in single-tenant, and is essential if you extend to multi-tenant later)
- Every data table keys off `connection_id` (FK to `qbo_connections`). All queries in `sync.js`/`projection.js` filter by `connection_id` — never a bare `SELECT * FROM invoice_snapshots`.
- If you extend to multi-tenant: add a `tenant_id`/`user_id` owner column on `qbo_connections`, enforce it in **every** query (not just at the API-route layer — consider PostgreSQL Row-Level Security policies keyed on a session variable set per request, as defense-in-depth against a missed `WHERE` clause).
- One realm/company's tokens are never usable to fetch another's data — `qboClient.js` always takes a `connection` object and derives `realmId`/token from it; there's no global/shared token.

**Transport & webhook considerations**
- All external calls (`api.intuit.com`, `oauth.platform.intuit.com`) over HTTPS only — this is the default for `https://` URLs and isn't something you can misconfigure by accident here, just don't downgrade it.
- Redirect URI must be HTTPS in production (§1) — prevents the authorization code from being exposed over plaintext HTTP.
- If you later add QBO webhooks for near-real-time updates (out of scope for this 30–60 min polling build), verify the `intuit-signature` HMAC header on every webhook payload before trusting it.

---

## Setup checklist (end-to-end)

1. Create Intuit Developer app, note `CLIENT_ID`/`CLIENT_SECRET` (§1).
2. Register redirect URI(s) for dev and prod.
3. `cp .env.example .env`, fill in `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`, `DATABASE_URL`, generate `TOKEN_ENCRYPTION_KEY` with `openssl rand -base64 32`.
4. `psql $DATABASE_URL -f db/schema.sql`
5. `npm install && npm run dev`
6. Visit `/connect`, approve against your Sandbox company, confirm redirect to `/connected`.
7. Confirm a manual sync works: `npm run sync:once` (or wait for the scheduler), check `bank_balance_snapshots`/`invoice_snapshots`/`bill_snapshots` are populated and `cash_flow_projections` has 13 rows.
8. Apply for Production keys once you're ready to point at a real company; swap env vars, re-run `/connect` against production.
