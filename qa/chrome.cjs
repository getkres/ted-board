// Test harness adapter: use installed Google Chrome, never bundled Chromium.
const playwright = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const launch = playwright.chromium.launch.bind(playwright.chromium);
playwright.chromium.launch = options => launch({...options, channel: 'chrome'});
module.exports = playwright;
