# Hello_world
The beginning of another long story

Hello all RunThenumBas here,

Currently invested in the trade welding and its great and all but I feel as though there are bigger and better opertunities out there then for me. I am very intriuded by the exploration of space, futher development in technoligy and upper limits to the human brain and what we can acheive as a collective. Learning to code I feel will give me a foot in the door towards pursuing one of those inerests if not all of them!

## QuickBooks Online 13-Week Cash Flow Projection

A read-only QuickBooks Online (QBO) integration that pulls bank balances, open
invoices, and unpaid bills to project cash-basis cash flow 13 weeks out.

- Full design doc (Intuit app setup, OAuth flow, scopes, endpoints, schema,
  security checklist, projection algorithm): [`docs/QBO_CASH_FLOW_INTEGRATION.md`](docs/QBO_CASH_FLOW_INTEGRATION.md)
- Starter implementation (Node.js + Express + PostgreSQL): [`src/`](src/), [`db/schema.sql`](db/schema.sql)

Quick start:

```bash
cp .env.example .env   # fill in QBO client id/secret, DATABASE_URL, TOKEN_ENCRYPTION_KEY, SESSION_SECRET
npm install
npm run migrate        # applies db/schema.sql
npm run dev             # starts the server, visit /connect to authorize QuickBooks
```
