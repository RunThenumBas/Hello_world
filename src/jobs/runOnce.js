// Manual one-off sync + projection run, for local testing: `npm run sync:once`
const { runCoreSync } = require('./scheduler');

runCoreSync()
  .then(() => {
    console.log('Sync + projection run complete.');
    process.exit(0);
  })
  .catch((err) => {
    console.error('Sync run failed:', err);
    process.exit(1);
  });
