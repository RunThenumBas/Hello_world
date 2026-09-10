const cron = require('node-cron');
const tokenStore = require('../services/tokenStore');
const sync = require('../services/sync');
const projection = require('../services/projection');
const auditLog = require('../services/auditLog');

// Core sync: bank balances, open invoices, open bills, then a fresh 13-week
// projection. Runs every 30 minutes.
async function runCoreSync() {
  const connection = await tokenStore.getActiveConnection();
  if (!connection) return;
  if (connection.status === 'needs_reauth') return;

  try {
    const fresh = await tokenStore.ensureFreshAccessToken(connection);
    await sync.pullBankBalances(fresh);
    await sync.pullOpenInvoices(fresh);
    await sync.pullOpenBills(fresh);
    await projection.buildThirteenWeekProjection(fresh);
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'core_sync',
      status: 'failure',
      detail: err.message,
    });
  }
}

// Historical payment data changes slowly -- pull once a day instead of every
// 30 minutes to stay well under QBO rate limits and avoid unnecessary load.
async function runDailyHistorySync() {
  const connection = await tokenStore.getActiveConnection();
  if (!connection) return;
  if (connection.status === 'needs_reauth') return;

  try {
    const fresh = await tokenStore.ensureFreshAccessToken(connection);
    await sync.pullPaymentHistory(fresh);
    await sync.recomputeDaysToPayStats(fresh);
  } catch (err) {
    await auditLog.write({
      connectionId: connection.id,
      action: 'daily_history_sync',
      status: 'failure',
      detail: err.message,
    });
  }
}

function start() {
  // Every 30 minutes.
  cron.schedule('*/30 * * * *', runCoreSync);
  // Once a day at 03:00 server time.
  cron.schedule('0 3 * * *', runDailyHistorySync);
}

module.exports = { start, runCoreSync, runDailyHistorySync };
