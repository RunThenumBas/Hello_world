require('dotenv').config();

function required(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

module.exports = {
  port: process.env.PORT || 3000,

  qbo: {
    clientId: required('QBO_CLIENT_ID'),
    clientSecret: required('QBO_CLIENT_SECRET'),
    environment: process.env.QBO_ENVIRONMENT || 'sandbox',
    redirectUri: required('QBO_REDIRECT_URI'),
  },

  databaseUrl: required('DATABASE_URL'),

  // 32 raw bytes, base64-encoded (openssl rand -base64 32).
  tokenEncryptionKey: Buffer.from(required('TOKEN_ENCRYPTION_KEY'), 'base64'),

  sessionSecret: required('SESSION_SECRET'),

  projection: {
    useDaysToPayAdjustment: process.env.USE_DAYS_TO_PAY_ADJUSTMENT === 'true',
    defaultPaymentTermDays: parseInt(process.env.DEFAULT_PAYMENT_TERM_DAYS || '30', 10),
  },
};
