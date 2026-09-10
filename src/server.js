const express = require('express');
const session = require('express-session');
const config = require('./config');
const authRoutes = require('./routes/auth');
const dashboardRoutes = require('./routes/dashboard');
const scheduler = require('./jobs/scheduler');

const app = express();

app.use(
  session({
    secret: config.sessionSecret,
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true, secure: config.qbo.environment === 'production' },
  })
);

app.use(authRoutes);
app.use(dashboardRoutes);

app.get('/health', (req, res) => res.json({ ok: true }));

app.listen(config.port, () => {
  console.log(`QBO cash flow app listening on port ${config.port}`);
  scheduler.start();
});
