// TS-first loader.
// Prefer the built TypeScript bundle; fall back to the classic JS app if the
// TS build is not available yet.

import('/static/dist/assets/app_mock.js').catch(() => import('/static/app.js'));
