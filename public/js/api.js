// API and Auth Client Helpers for vMix Switcher

const API = {
  TOKEN_KEY: 'vmix_switcher_token',

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  },

  clearToken() {
    localStorage.removeItem(this.TOKEN_KEY);
  },

  async request(endpoint, options = {}) {
    const token = this.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(endpoint, {
        ...options,
        headers
      });

      if (response.status === 401) {
        this.clearToken();
        window.dispatchEvent(new CustomEvent('auth:required'));
        throw new Error('Unauthorized');
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      return data;
    } catch (err) {
      throw err;
    }
  },

  async login(password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Login failed');
    }

    this.setToken(data.token);
    return data;
  },

  async checkAuth() {
    const token = this.getToken();
    if (!token) return false;
    try {
      const res = await this.request('/api/auth/check');
      return Boolean(res.authenticated);
    } catch {
      return false;
    }
  },

  logout() {
    this.clearToken();
    window.location.reload();
  },

  // vMix Controls
  async getState() {
    return this.request('/api/vmix/state');
  },

  async switchInput(input, transition, duration) {
    return this.request('/api/vmix/switch', {
      method: 'POST',
      body: JSON.stringify({ input, transition, duration })
    });
  },

  async executeFunction(functionName, params = {}) {
    return this.request('/api/vmix/function', {
      method: 'POST',
      body: JSON.stringify({ function: functionName, params })
    });
  },

  async toggleOverlay(overlay, input) {
    return this.request('/api/vmix/overlay', {
      method: 'POST',
      body: JSON.stringify({ overlay, input })
    });
  },

  async toggleAudio(input) {
    return this.request('/api/vmix/audio', {
      method: 'POST',
      body: JSON.stringify({ input })
    });
  },

  getThumbnailUrl(input) {
    const token = this.getToken() || '';
    return `/api/vmix/thumbnail/${encodeURIComponent(input)}?token=${encodeURIComponent(token)}`;
  },

  // Source Management (App-side ignore/hide)
  async setSourceIgnored(input, ignore) {
    return this.request('/api/sources/ignore', {
      method: 'POST',
      body: JSON.stringify({ input, ignore })
    });
  },

  async unignoreAllSources() {
    return this.request('/api/sources/unignore-all', {
      method: 'POST'
    });
  },

  async setSourceAlias(input, name) {
    return this.request('/api/sources/alias', {
      method: 'POST',
      body: JSON.stringify({ input, name })
    });
  },

  // Configuration
  async getConfig() {
    return this.request('/api/config');
  },

  async saveConfig(updates) {
    return this.request('/api/config', {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  },

  async getNetworkIps() {
    return this.request('/api/system/network');
  }
};
