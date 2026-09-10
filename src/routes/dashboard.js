const express = require('express');
const { pool } = require('../db/pool');
const tokenStore = require('../services/tokenStore');

const router = express.Router();

// Returns the most recent 13-week projection for the active connection.
router.get('/api/projection', async (req, res) => {
  const connection = await tokenStore.getActiveConnection();
  if (!connection) {
    return res.status(404).json({ error: 'No active QuickBooks connection.' });
  }

  const latestRun = await pool.query(
    `SELECT MAX(run_at) AS run_at FROM cash_flow_projections WHERE connection_id = $1`,
    [connection.id]
  );
  const runAt = latestRun.rows[0].run_at;
  if (!runAt) {
    return res.status(404).json({ error: 'No projection has been generated yet.' });
  }

  const rows = await pool.query(
    `SELECT week_index, week_start_date, starting_balance, projected_inflows,
            projected_outflows, ending_balance
     FROM cash_flow_projections
     WHERE connection_id = $1 AND run_at = $2
     ORDER BY week_index ASC`,
    [connection.id, runAt]
  );

  res.json({
    companyName: connection.companyName,
    runAt,
    weeks: rows.rows,
  });
});

module.exports = router;
