const fetch = require('node-fetch');
const { pool } = require('../db/pool');
const { encrypt, decrypt } = require('./crypto');
const auditLog = require('./auditLog');
const config = require('../config');

const TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer';
const REFRESH_SAFETY_WINDOW_MS = 2 * 60 * 1000; // refresh if within 2 min of expiry

function basicAuthHeader() {
  const raw = `${config.qbo.clientId}:${config.qbo.clientSecret}`;
  return `Basic ${Buffer.from(raw, 'utf8').toString('base64')}`;
}

async function exchangeCodeForTokens(code) {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: config.qbo.redirectUri,
  });
  return postTokenRequest(body);
}

async function refreshTokens(refreshToken) {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
  });
  return postTokenRequest(body);
}

async function postTokenRequest(body) {
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: {
      Authorization: basicAuthHeader(),
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    const err = new Error(`QBO token request failed: ${res.status}`);
    err.status = res.status;
    err.body = text;
    throw err;
  }
  return res.json();
}

// Persists a brand-new connection after the initial /callback exchange.
async function saveNewConnection({ realmId, companyName, tokenResponse }) {
  const now = Date.now();
  const accessTokenExpiresAt = new Date(now + tokenResponse.expires_in * 1000);
  const refreshTokenExpiresAt = new Date(now + tokenResponse.x_refresh_token_expires_in * 1000);

  const result = await pool.query(
    `INSERT INTO qbo_connections
       (realm_id, company_name, access_token_ciphertext, access_token_expires_at,
        refresh_token_ciphertext, refresh_token_expires_at, status)
     VALUES ($1, $2, $3, $4, $5, $6, 'active')
     ON CONFLICT (realm_id) DO UPDATE SET
       company_name = EXCLUDED.company_name,
       access_token_ciphertext = EXCLUDED.access_token_ciphertext,
       access_token_expires_at = EXCLUDED.access_token_expires_at,
       refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
       refresh_token_expires_at = EXCLUDED.refresh_token_expires_at,
       status = 'active',
       updated_at = now()
     RETURNING id`,
    [
      realmId,
      companyName,
      encrypt(tokenResponse.access_token),
      accessTokenExpiresAt,
      encrypt(tokenResponse.refresh_token),
      refreshTokenExpiresAt,
    ]
  );
  return result.rows[0].id;
}

// Single-tenant build: there is one active connection at a time.
async function getActiveConnection() {
  const result = await pool.query(
    `SELECT * FROM qbo_connections WHERE status = 'active' ORDER BY created_at DESC LIMIT 1`
  );
  if (result.rows.length === 0) return null;
  return toConnectionView(result.rows[0]);
}

function toConnectionView(row) {
  return {
    id: row.id,
    realmId: row.realm_id,
    companyName: row.company_name,
    accessToken: decrypt(row.access_token_ciphertext),
    accessTokenExpiresAt: row.access_token_expires_at,
    refreshToken: decrypt(row.refresh_token_ciphertext),
    refreshTokenExpiresAt: row.refresh_token_expires_at,
    status: row.status,
  };
}

// Ensures connection.accessToken is valid for the next few minutes,
// refreshing (and persisting the rotated refresh token) if needed.
async function ensureFreshAccessToken(connection) {
  const expiresAt = new Date(connection.accessTokenExpiresAt).getTime();
  if (expiresAt - Date.now() > REFRESH_SAFETY_WINDOW_MS) {
    return connection; // still valid
  }

  try {
    const tokenResponse = await refreshTokens(connection.refreshToken);
    const now = Date.now();
    const accessTokenExpiresAt = new Date(now + tokenResponse.expires_in * 1000);
    const refreshTokenExpiresAt = new Date(now + tokenResponse.x_refresh_token_expires_in * 1000);

    await pool.query(
      `UPDATE qbo_connections SET
         access_token_ciphertext = $1,
         access_token_expires_at = $2,
         refresh_token_ciphertext = $3,
         refresh_token_expires_at = $4,
         status = 'active',
         updated_at = now()
       WHERE id = $5`,
      [
        encrypt(tokenResponse.access_token),
        accessTokenExpiresAt,
        encrypt(tokenResponse.refresh_token),
        refreshTokenExpiresAt,
        connection.id,
      ]
    );
    await auditLog.write({ connectionId: connection.id, action: 'token_refresh', status: 'success' });

    return {
      ...connection,
      accessToken: tokenResponse.access_token,
      accessTokenExpiresAt,
      refreshToken: tokenResponse.refresh_token,
      refreshTokenExpiresAt,
    };
  } catch (err) {
    // invalid_grant (400/401) means the refresh token is dead — user must reconnect.
    if (err.status === 400 || err.status === 401) {
      await pool.query(`UPDATE qbo_connections SET status = 'needs_reauth', updated_at = now() WHERE id = $1`, [
        connection.id,
      ]);
    }
    await auditLog.write({
      connectionId: connection.id,
      action: 'token_refresh',
      status: 'failure',
      detail: `${err.status || ''} ${err.message}`.trim(),
    });
    throw err;
  }
}

async function markDisconnected(connectionId) {
  await pool.query(`UPDATE qbo_connections SET status = 'disconnected', updated_at = now() WHERE id = $1`, [
    connectionId,
  ]);
}

module.exports = {
  exchangeCodeForTokens,
  saveNewConnection,
  getActiveConnection,
  ensureFreshAccessToken,
  markDisconnected,
};
