/**
 * AuthHub browser client.
 * AuthHub owns provider auth, signup/login classification and session exchange.
 * Projects consume the final authenticated session; do not duplicate provider-specific auth logic.
 */
export class AuthHubClient {
  constructor({ apiBase, project, environment = 'production', storage = globalThis.localStorage } = {}) {
    this.apiBase = String(apiBase || '').replace(/\/$/, '');
    this.project = String(project || '').trim();
    this.environment = String(environment || 'production');
    this.storage = storage;
    if (!this.apiBase || !this.project) throw new Error('apiBase and project are required');
    this.key = `authhub:${this.project}:${this.environment}:session`;
  }
  url(path) {
    const u = new URL(`${this.apiBase}${path}`);
    u.searchParams.set('environment', this.environment);
    return u.toString();
  }
  async request(path, options = {}) {
    const headers = { 'content-type': 'application/json', ...(options.headers || {}) };
    const session = this.session();
    if (session?.accessToken) headers.authorization = `Bearer ${session.accessToken}`;
    const res = await fetch(this.url(path), { ...options, headers });
    const raw = await res.text(); let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch { body = { error: raw || 'request_failed' }; }
    if (!res.ok) throw Object.assign(new Error(body.error || `AuthHub request failed (${res.status})`), { status: res.status, body });
    return body;
  }
  config() { return this.request(`/v1/config/${encodeURIComponent(this.project)}`); }
  async signup({ email, password, displayName = '' }) {
    return this.save(await this.request(`/v1/auth/${encodeURIComponent(this.project)}/signup`, { method: 'POST', body: JSON.stringify({ email, password, displayName }) }));
  }
  async login({ email, password }) {
    return this.save(await this.request(`/v1/auth/${encodeURIComponent(this.project)}/login`, { method: 'POST', body: JSON.stringify({ email, password }) }));
  }
  startOAuth(provider, { redirectUri = location.href, state = '' } = {}) {
    const u = new URL(this.url(`/v1/oauth/${encodeURIComponent(this.project)}/${encodeURIComponent(provider)}/start`));
    u.searchParams.set('redirect_uri', redirectUri);
    if (state) u.searchParams.set('state', state);
    location.assign(u.toString());
  }
  async exchange(code) {
    return this.save(await this.request(`/v1/auth/${encodeURIComponent(this.project)}/exchange`, { method: 'POST', body: JSON.stringify({ code }) }));
  }
  async externalToken(token) {
    return this.save(await this.request(`/v1/auth/${encodeURIComponent(this.project)}/external-token`, { method: 'POST', body: JSON.stringify({ token }) }));
  }
  async refresh() {
    const current = this.session(); if (!current?.refreshToken) throw new Error('refresh token is missing');
    return this.save(await this.request(`/v1/auth/${encodeURIComponent(this.project)}/refresh`, { method: 'POST', body: JSON.stringify({ refreshToken: current.refreshToken }) }));
  }
  async me() { return this.request('/v1/me'); }
  async logout() {
    const current = this.session();
    try { if (current?.refreshToken) await this.request(`/v1/auth/${encodeURIComponent(this.project)}/logout`, { method: 'POST', body: JSON.stringify({ refreshToken: current.refreshToken }) }); }
    finally { this.storage?.removeItem(this.key); }
  }
  session() {
    try { return JSON.parse(this.storage?.getItem(this.key) || 'null'); } catch { return null; }
  }
  save(session) {
    if (session?.accessToken && this.storage) this.storage.setItem(this.key, JSON.stringify(session));
    return session;
  }
  async consumeOAuthCallback(url = location.href) {
    const u = new URL(url); const error = u.searchParams.get('error');
    if (error) throw new Error(error);
    if (u.searchParams.get('status') === 'pending_approval') return { pendingApproval: true, state: u.searchParams.get('state') || '' };
    const code = u.searchParams.get('code'); if (!code) return null;
    const session = await this.exchange(code);
    return { ...session, onboarding: session?.onboarding || { isNewUser: false, isNewMembership: false, provider: '' }, state: u.searchParams.get('state') || '' };
  }
}
