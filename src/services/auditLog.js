// Audit trail for OAuth + sync events. Never pass token values, headers, or
// full API response bodies as `detail` — only short, non-sensitive summaries
// (row counts, error class/message).
const { pool } = require('../db/pool');

async function write({ connectionId = null, action, status, detail = null }) {
  await pool.query(
    `INSERT INTO sync_audit_log (connection_id, action, status, detail)
     VALUES ($1, $2, $3, $4)`,
    [connectionId, action, status, detail]
  );
}

module.exports = { write };
