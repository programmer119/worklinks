import assert from 'node:assert/strict';

// No browser or personal account is needed for this deterministic routing test.
const storage = new Map();
globalThis.document = { getElementById: () => null };
globalThis.localStorage = {
  getItem: (key) => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, String(value))
};
const {worklinksHostedAuthUrl, rememberWorklinksAuthProvider} =
  await import('../startup-support/worklinks-header-auth.js');

function assertLogin(url, provider) {
  const u = new URL(url);
  assert.equal(u.origin, 'https://api-authhub.suaveforge.com');
  assert.equal(u.pathname, '/v1/oauth/p47/' + provider + '/start');
  assert.equal(u.searchParams.get('environment'), 'production');
  assert.equal(u.searchParams.get('redirect_uri'),
    'https://worklinks.suaveforge.com/startup-support/auth-callback.html');
  assert.equal(u.searchParams.get('state'), '/startup-support/');
}
let u = new URL(worklinksHostedAuthUrl('login'));
assert.equal(u.origin, 'https://authhub.suaveforge.com');
assert.equal(u.pathname, '/login/');
assert.equal(u.searchParams.get('mode'), 'login');

for (const provider of ['google', 'kakao', 'naver', 'microsoft', 'apple']) {
  rememberWorklinksAuthProvider(provider);
  assertLogin(worklinksHostedAuthUrl('login'), provider);
  const signUp = new URL(worklinksHostedAuthUrl('signup'));
  assert.equal(signUp.origin, 'https://authhub.suaveforge.com');
  assert.equal(signUp.searchParams.get('mode'), 'signup');
}
// Do not silently change an email/password member to a different social identity.
rememberWorklinksAuthProvider('password');
u = new URL(worklinksHostedAuthUrl('login'));
assert.equal(u.origin, 'https://authhub.suaveforge.com');
assert.equal(u.searchParams.get('mode'), 'login');
rememberWorklinksAuthProvider('unsupported');
assert.equal(new URL(worklinksHostedAuthUrl('login')).origin,
  'https://authhub.suaveforge.com');

// Only a successful AuthHub callback saves a verified provider; never a
// requested URL, unverified email address, provider token or password.
console.log('WORKLINKS_DIRECT_RELOGIN_PROVIDER_ROUTES=PASS');
