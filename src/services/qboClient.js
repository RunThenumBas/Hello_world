// Thin QBO Accounting API client. Intentionally exposes ONLY read operations
// (get/queryAll) -- there is no post/put/delete method in this module, so a
// write call would require adding new code, not just calling something that
// already exists. This is the code-level enforcement of "read-only" described
// in docs/QBO_CASH_FLOW_INTEGRATION.md section 3.
const fetch = require('node-fetch');
const config = require('../config');

const MAX_RESULTS = 1000;

function apiBaseUrl() {
  return config.qbo.environment === 'production'
    ? 'https://quickbooks.api.intuit.com'
    : 'https://sandbox-quickbooks.api.intuit.com';
}

async function get(connection, path) {
  const url = `${apiBaseUrl()}/v3/company/${connection.realmId}${path}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${connection.accessToken}`,
      Accept: 'application/json',
    },
  });
  if (!res.ok) {
    const text = await res.text();
    const err = new Error(`QBO API request failed: ${res.status}`);
    err.status = res.status;
    err.body = text;
    throw err;
  }
  return res.json();
}

// Auto-paginating wrapper around the Query endpoint. `baseQuery` should be a
// full SOQL query WITHOUT STARTPOSITION/MAXRESULTS (those are added here).
async function queryAll(connection, baseQuery, entityKey) {
  const results = [];
  let startPosition = 1;

  // Safety cap so a bug or an unexpectedly huge company can't spin forever.
  for (let page = 0; page < 1000; page++) {
    const query = `${baseQuery} STARTPOSITION ${startPosition} MAXRESULTS ${MAX_RESULTS}`;
    const path = `/query?query=${encodeURIComponent(query)}`;
    const data = await get(connection, path);
    const rows = (data.QueryResponse && data.QueryResponse[entityKey]) || [];
    results.push(...rows);

    if (rows.length < MAX_RESULTS) break;
    startPosition += MAX_RESULTS;
  }

  return results;
}

module.exports = { get, queryAll };
