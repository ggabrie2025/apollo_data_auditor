// auth.js - API Key Management via LocalStorage
// Agent Cloud V1.6 - Same pattern as Apollo Cloud Dashboard
// (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr

const AUTH = {
  KEY_STORAGE: 'apollo_agent_api_key',
  HUB_URL: 'https://apollo-cloud-api-production.up.railway.app',

  // Get stored API key
  getApiKey() {
    return localStorage.getItem(this.KEY_STORAGE);
  },

  // Store API key
  setApiKey(apiKey) {
    localStorage.setItem(this.KEY_STORAGE, apiKey);
  },

  // Sprint 91: Clear API key + tier (logout) — also resets server-side key
  clearApiKey() {
    localStorage.removeItem(this.KEY_STORAGE);
    localStorage.removeItem(this.TIER_STORAGE);
    // Reset server-side _active_api_key (fire-and-forget)
    fetch('/api/v2/logout', { method: 'POST' }).catch(() => {});
  },

  // Check if authenticated
  isAuthenticated() {
    return !!this.getApiKey();
  },

  // Sprint 91: Validate API key via server set-api-key endpoint
  // Sends key to server, server validates via Hub /me, stores as _active_api_key
  async validateApiKey(apiKey) {
    try {
      const response = await fetch('/api/v2/set-api-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey })
      });
      if (!response.ok) return false;
      const data = await response.json();
      // Store tier from Hub validation
      if (data.tier) {
        this.setTier(data.tier);
      }
      if (data.is_admin) {
        this.setTier('enterprise');
      }
      return data.status === 'ok';
    } catch (error) {
      console.error('[AUTH] Validation failed:', error);
      return false;
    }
  },

  // Require authentication (redirect if missing)
  requireAuth() {
    if (!this.isAuthenticated()) {
      window.location.href = '/static/login.html';
    }
  },

  // Sprint 88B: Tier management (free/starter/business/enterprise)
  TIER_STORAGE: 'apollo_agent_tier',

  setTier(tier) {
    localStorage.setItem(this.TIER_STORAGE, tier);
  },

  getTier() {
    return localStorage.getItem(this.TIER_STORAGE) || 'free';
  },

  clearTier() {
    localStorage.removeItem(this.TIER_STORAGE);
  }
};
