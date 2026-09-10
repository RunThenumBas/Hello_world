const { pool, withTransaction } = require('../db/pool');
const qboClient = require('./qboClient');
const auditLog = require('./auditLog');

async function pullBankBalances(connection) {
  try {
    const rows = await qboClient.queryAll(
      connection,
      "SELECT * FROM Account WHERE AccountType IN ('Bank') AND Active = true",
      'Account'
    );
    const snapshotAt = new Date();

    await withTransaction(async (trx) => {
      for (const acct of rows) {
        await trx.query(
          `INSERT INTO bank_balance_snapshots
             (connection_id, qbo_account_id, account_name, current_balance, snapshot_at)
           VALUES ($1, $2, $3, $4, $5)`,
          [connection.id, acct.Id, acct.Name, acct.CurrentBalance || 0, snapshotAt]
        );
      }
    });

    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_balances',
      status: 'success',
      detail: `${rows.length} accounts`,
    });
    return rows.length;
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_balances',
      status: 'failure',
      detail: err.message,
    });
    throw err;
  }
}

async function pullOpenInvoices(connection) {
  try {
    const rows = await qboClient.queryAll(connection, "SELECT * FROM Invoice WHERE Balance > '0'", 'Invoice');
    const snapshotAt = new Date();

    await withTransaction(async (trx) => {
      for (const inv of rows) {
        await trx.query(
          `INSERT INTO invoice_snapshots
             (connection_id, qbo_invoice_id, doc_number, customer_qbo_id, customer_name,
              txn_date, due_date, open_balance, total_amt, snapshot_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (connection_id, qbo_invoice_id, snapshot_at) DO NOTHING`,
          [
            connection.id,
            inv.Id,
            inv.DocNumber,
            inv.CustomerRef && inv.CustomerRef.value,
            inv.CustomerRef && inv.CustomerRef.name,
            inv.TxnDate,
            inv.DueDate,
            inv.Balance,
            inv.TotalAmt,
            snapshotAt,
          ]
        );
      }
    });

    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_invoices',
      status: 'success',
      detail: `${rows.length} open invoices`,
    });
    return rows.length;
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_invoices',
      status: 'failure',
      detail: err.message,
    });
    throw err;
  }
}

async function pullOpenBills(connection) {
  try {
    const rows = await qboClient.queryAll(connection, "SELECT * FROM Bill WHERE Balance > '0'", 'Bill');
    const snapshotAt = new Date();

    await withTransaction(async (trx) => {
      for (const bill of rows) {
        await trx.query(
          `INSERT INTO bill_snapshots
             (connection_id, qbo_bill_id, doc_number, vendor_qbo_id, vendor_name,
              txn_date, due_date, open_balance, total_amt, snapshot_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (connection_id, qbo_bill_id, snapshot_at) DO NOTHING`,
          [
            connection.id,
            bill.Id,
            bill.DocNumber,
            bill.VendorRef && bill.VendorRef.value,
            bill.VendorRef && bill.VendorRef.name,
            bill.TxnDate,
            bill.DueDate,
            bill.Balance,
            bill.TotalAmt,
            snapshotAt,
          ]
        );
      }
    });

    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_bills',
      status: 'success',
      detail: `${rows.length} open bills`,
    });
    return rows.length;
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_bills',
      status: 'failure',
      detail: err.message,
    });
    throw err;
  }
}

function daysBetween(a, b) {
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  return Math.round((new Date(b) - new Date(a)) / MS_PER_DAY);
}

// Extracts the first linked invoice/bill id + date from a Payment/BillPayment
// Line[].LinkedTxn[] structure, if present.
function firstLinkedTxn(payment) {
  const lines = payment.Line || [];
  for (const line of lines) {
    const linked = (line.LinkedTxn || [])[0];
    if (linked) return linked;
  }
  return null;
}

async function pullPaymentHistory(connection) {
  const oneYearAgo = new Date();
  oneYearAgo.setDate(oneYearAgo.getDate() - 365);
  const since = oneYearAgo.toISOString().slice(0, 10);

  try {
    const [payments, billPayments] = await Promise.all([
      qboClient.queryAll(connection, `SELECT * FROM Payment WHERE TxnDate >= '${since}'`, 'Payment'),
      qboClient.queryAll(connection, `SELECT * FROM BillPayment WHERE TxnDate >= '${since}'`, 'BillPayment'),
    ]);

    await withTransaction(async (trx) => {
      // Clear and reload -- this table is a rolling 12-month history, not a
      // point-in-time snapshot series, so a full refresh each run is simplest.
      await trx.query(`DELETE FROM payment_history WHERE connection_id = $1`, [connection.id]);

      for (const p of payments) {
        const linked = firstLinkedTxn(p);
        await trx.query(
          `INSERT INTO payment_history
             (connection_id, direction, counterparty_qbo_id, counterparty_name,
              linked_invoice_or_bill_id, invoice_or_bill_date, payment_date, amount, days_to_pay)
           VALUES ($1, 'inflow', $2, $3, $4, $5, $6, $7, $8)`,
          [
            connection.id,
            p.CustomerRef && p.CustomerRef.value,
            p.CustomerRef && p.CustomerRef.name,
            linked && linked.TxnId,
            null, // QBO's LinkedTxn doesn't include the linked txn's date directly
            p.TxnDate,
            p.TotalAmt,
            null,
          ]
        );
      }

      for (const bp of billPayments) {
        const linked = firstLinkedTxn(bp);
        await trx.query(
          `INSERT INTO payment_history
             (connection_id, direction, counterparty_qbo_id, counterparty_name,
              linked_invoice_or_bill_id, invoice_or_bill_date, payment_date, amount, days_to_pay)
           VALUES ($1, 'outflow', $2, $3, $4, $5, $6, $7, $8)`,
          [
            connection.id,
            bp.VendorRef && bp.VendorRef.value,
            bp.VendorRef && bp.VendorRef.name,
            linked && linked.TxnId,
            null,
            bp.TxnDate,
            bp.TotalAmt,
            null,
          ]
        );
      }
    });

    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_payment_history',
      status: 'success',
      detail: `${payments.length} payments, ${billPayments.length} bill payments`,
    });
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'pull_payment_history',
      status: 'failure',
      detail: err.message,
    });
    throw err;
  }
}

// Recomputes avg/median days-to-pay per counterparty from payment_history
// rows that have a resolved invoice_or_bill_date. Note: the basic pullPaymentHistory
// above does not resolve linked_invoice_or_bill_id -> its date; a production
// build should join linked_invoice_or_bill_id against invoice_snapshots /
// bill_snapshots (matching on qbo_invoice_id / qbo_bill_id) before this runs,
// so days_to_pay can be computed. This function is intentionally simple and
// skips rows where days_to_pay is still null.
async function recomputeDaysToPayStats(connection) {
  const result = await pool.query(
    `SELECT counterparty_qbo_id, direction,
            AVG(days_to_pay)::numeric(6,1) AS avg_days,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_to_pay)::numeric(6,1) AS median_days,
            COUNT(*) AS sample_size
     FROM payment_history
     WHERE connection_id = $1 AND days_to_pay IS NOT NULL
     GROUP BY counterparty_qbo_id, direction`,
    [connection.id]
  );

  await withTransaction(async (trx) => {
    for (const row of result.rows) {
      const counterpartyType = row.direction === 'inflow' ? 'customer' : 'vendor';
      await trx.query(
        `INSERT INTO days_to_pay_stats
           (connection_id, counterparty_qbo_id, counterparty_type, avg_days_to_pay, median_days_to_pay, sample_size, computed_at)
         VALUES ($1, $2, $3, $4, $5, $6, now())
         ON CONFLICT (connection_id, counterparty_qbo_id) DO UPDATE SET
           avg_days_to_pay = EXCLUDED.avg_days_to_pay,
           median_days_to_pay = EXCLUDED.median_days_to_pay,
           sample_size = EXCLUDED.sample_size,
           computed_at = now()`,
        [connection.id, row.counterparty_qbo_id, counterpartyType, row.avg_days, row.median_days, row.sample_size]
      );
    }
  });

  await auditLog.write({
    connectionId: connection.id,
    action: 'recompute_days_to_pay_stats',
    status: 'success',
    detail: `${result.rows.length} counterparties`,
  });
}

module.exports = {
  pullBankBalances,
  pullOpenInvoices,
  pullOpenBills,
  pullPaymentHistory,
  recomputeDaysToPayStats,
};
