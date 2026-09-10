const express = require('express');
const crypto = require('crypto');
const config = require('../config');
const tokenStore = require('../services/tokenStore');
const qboClient = require('../services/qboClient');
const auditLog = require('../services/auditLog');

const router = express.Router();

const AUTHORIZE_URL = 'https://appcenter.intuit.com/connect/oauth2';

// Step 1: send the user to Intuit's consent screen.
router.get('/connect', (req, res) => {
  const state = crypto.randomBytes(16).toString('hex');
  req.session.oauthState = state;

  const params = new URLSearchParams({
    client_id: config.qbo.clientId,
    redirect_uri: config.qbo.redirectUri,
    response_type: 'code',
    scope: 'com.intuit.quickbooks.accounting',
    state,
  });

  res.redirect(`${AUTHORIZE_URL}?${params.toString()}`);
});

// Step 2: Intuit redirects back here with ?code&state&realmId (or ?error).
router.get('/callback', async (req, res) => {
  const { code, state, realmId, error } = req.query;

  if (error) {
    return res.status(400).send('QuickBooks authorization was denied or failed.');
  }
  if (!state || state !== req.session.oauthState) {
    await auditLog.write({ action: 'connect', status: 'failure', detail: 'state mismatch' });
    return res.status(401).send('Invalid OAuth state.');
  }
  if (!code || !realmId) {
    return res.status(400).send('Missing code or realmId from QuickBooks callback.');
  }

  try {
    const tokenResponse = await tokenStore.exchangeCodeForTokens(code);
    const connectionId = await tokenStore.saveNewConnection({
      realmId,
      companyName: null,
      tokenResponse,
    });

    // Fetch company name once, for display purposes, using the new connection.
    try {
      const connection = await tokenStore.getActiveConnection();
      const info = await qboClient.get(connection, `/companyinfo/${realmId}`);
      const companyName = info.CompanyInfo && info.CompanyInfo.CompanyName;
      if (companyName) {
        await tokenStore.saveNewConnection({ realmId, companyName, tokenResponse });
      }
    } catch (infoErr) {
      // Non-fatal -- the connection is still usable without a display name.
      await auditLog.write({
        connectionId,
        action: 'fetch_company_info',
        status: 'failure',
        detail: infoErr.message,
      });
    }

    delete req.session.oauthState;
    await auditLog.write({ connectionId, action: 'connect', status: 'success' });
    res.redirect('/connected');
  } catch (err) {
    await auditLog.write({ action: 'connect', status: 'failure', detail: err.message });
    res.status(502).send('Failed to complete QuickBooks authorization.');
  }
});

router.get('/connected', (req, res) => {
  res.send('QuickBooks account connected successfully.');
});

router.post('/disconnect', async (req, res) => {
  const connection = await tokenStore.getActiveConnection();
  if (connection) {
    await tokenStore.markDisconnected(connection.id);
    await auditLog.write({ connectionId: connection.id, action: 'disconnect', status: 'success' });
  }
  res.send('Disconnected.');
});

module.exports = router;
