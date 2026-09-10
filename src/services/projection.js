const { pool, withTransaction } = require('../db/pool');
const auditLog = require('./auditLog');
const config = require('../config');

const NUM_WEEKS = 13;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function startOfDay(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(date, days) {
  return new Date(date.getTime() + days * MS_PER_DAY);
}

function buildWeekBuckets(today) {
  const buckets = [];
  for (let i = 0; i < NUM_WEEKS; i++) {
    buckets.push(addDays(today, 7 * i));
  }
  return buckets;
}

// Returns the index (0..12) of the week bucket a date falls into, clamped to
// the array bounds -- anything before today lands in week 0 (see docs section 7),
// anything after week 12's end also lands in week 12 rather than being dropped.
function weekIndexFor(date, weekBuckets) {
  for (let i = weekBuckets.length - 1; i >= 0; i--) {
    if (date >= weekBuckets[i]) return i;
  }
  return 0;
}

async function latestSnapshotRows(client, connectionId, table) {
  const latest = await client.query(
    `SELECT MAX(snapshot_at) AS latest FROM ${table} WHERE connection_id = $1`,
    [connectionId]
  );
  const latestAt = latest.rows[0].latest;
  if (!latestAt) return [];

  const rows = await client.query(`SELECT * FROM ${table} WHERE connection_id = $1 AND snapshot_at = $2`, [
    connectionId,
    latestAt,
  ]);
  return rows.rows;
}

async function loadDaysToPayStats(client, connectionId) {
  const result = await client.query(`SELECT * FROM days_to_pay_stats WHERE connection_id = $1`, [connectionId]);
  const map = new Map();
  for (const row of result.rows) {
    map.set(row.counterparty_qbo_id, row);
  }
  return map;
}

function expectedDate(item, { txnDateField, dueDateField, counterpartyIdField }, statsMap, today) {
  let expected = item[dueDateField] ? new Date(item[dueDateField]) : null;

  if (!expected) {
    // No due date at all -- fall back to txn date + default term.
    const txnDate = item[txnDateField] ? new Date(item[txnDateField]) : today;
    expected = addDays(txnDate, config.projection.defaultPaymentTermDays);
  }

  if (config.projection.useDaysToPayAdjustment) {
    const stats = statsMap.get(item[counterpartyIdField]);
    if (stats && stats.sample_size >= 3 && item[txnDateField]) {
      const adjusted = addDays(new Date(item[txnDateField]), Math.round(Number(stats.avg_days_to_pay)));
      expected = adjusted;
    }
  }

  return expected < today ? today : expected;
}

async function buildThirteenWeekProjection(connection) {
  const runAt = new Date();
  const today = startOfDay(runAt);
  const weekBuckets = buildWeekBuckets(today);

  const client = await pool.connect();
  try {
    const bankRows = await latestSnapshotRows(client, connection.id, 'bank_balance_snapshots');
    const invoiceRows = await latestSnapshotRows(client, connection.id, 'invoice_snapshots');
    const billRows = await latestSnapshotRows(client, connection.id, 'bill_snapshots');
    const statsMap = await loadDaysToPayStats(client, connection.id);

    const startingCash = bankRows.reduce((sum, r) => sum + Number(r.current_balance), 0);

    const inflowsByWeek = new Array(NUM_WEEKS).fill(0);
    for (const inv of invoiceRows) {
      const expected = expectedDate(
        inv,
        { txnDateField: 'txn_date', dueDateField: 'due_date', counterpartyIdField: 'customer_qbo_id' },
        statsMap,
        today
      );
      const idx = weekIndexFor(expected, weekBuckets);
      inflowsByWeek[idx] += Number(inv.open_balance);
    }

    const outflowsByWeek = new Array(NUM_WEEKS).fill(0);
    for (const bill of billRows) {
      const expected = expectedDate(
        bill,
        { txnDateField: 'txn_date', dueDateField: 'due_date', counterpartyIdField: 'vendor_qbo_id' },
        statsMap,
        today
      );
      const idx = weekIndexFor(expected, weekBuckets);
      outflowsByWeek[idx] += Number(bill.open_balance);
    }

    const results = [];
    let runningBalance = startingCash;
    for (let i = 0; i < NUM_WEEKS; i++) {
      const startingBalance = runningBalance;
      const inflow = inflowsByWeek[i];
      const outflow = outflowsByWeek[i];
      runningBalance = runningBalance + inflow - outflow;
      results.push({
        weekIndex: i,
        weekStartDate: weekBuckets[i].toISOString().slice(0, 10),
        startingBalance,
        projectedInflows: inflow,
        projectedOutflows: outflow,
        endingBalance: runningBalance,
      });
    }

    await withTransaction(async (trx) => {
      for (const r of results) {
        await trx.query(
          `INSERT INTO cash_flow_projections
             (connection_id, run_at, week_start_date, week_index, starting_balance,
              projected_inflows, projected_outflows, ending_balance)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
          [
            connection.id,
            runAt,
            r.weekStartDate,
            r.weekIndex,
            r.startingBalance,
            r.projectedInflows,
            r.projectedOutflows,
            r.endingBalance,
          ]
        );
      }
    });

    await auditLog.write({
      connectionId: connection.id,
      action: 'projection_run',
      status: 'success',
      detail: `starting_cash=${startingCash.toFixed(2)}, ${invoiceRows.length} invoices, ${billRows.length} bills`,
    });

    return results;
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'projection_run',
      status: 'failure',
      detail: err.message,
    });
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { buildThirteenWeekProjection };
