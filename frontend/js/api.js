/**
 * MediCare AI - Core API Client & State Management
 * Pure Vanilla JavaScript (ES6)
 */

const API_BASE_URL = (window.location.origin.startsWith('http')) 
  ? `${window.location.origin}/api` 
  : 'http://localhost:5000/api';

const TOKEN_KEY = 'medicare_access_token';
const USER_KEY = 'medicare_user_profile';

// Central API Service
const api = {
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },

  setToken(token) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  },

  getUser() {
    try {
      const data = localStorage.getItem(USER_KEY);
      return data ? JSON.parse(data) : null;
    } catch (e) {
      return null;
    }
  },

  setUser(user) {
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(USER_KEY);
    }
  },

  isAuthenticated() {
    return Boolean(this.getToken());
  },

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    showToast('You have been logged out.', 'info');
    setTimeout(() => {
      window.location.href = 'login.html';
    }, 800);
  },

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
    const headers = options.headers || {};

    const token = this.getToken();
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const config = {
      ...options,
      headers
    };

    try {
      const response = await fetch(url, config);
      const isJson = response.headers.get('content-type')?.includes('application/json');
      const data = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        if (response.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/register')) {
          // Token expired or invalid
          this.setToken(null);
          this.setUser(null);
          showToast('Session expired. Please log in again.', 'warning');
          setTimeout(() => {
            if (!window.location.pathname.endsWith('login.html')) {
              window.location.href = 'login.html';
            }
          }, 1200);
        }
        const errorMsg = data?.detail || data?.message || 'Server returned an error request.';
        throw new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
      }

      return data;
    } catch (err) {
      throw err;
    }
  },

  get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },

  post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: (body instanceof FormData) ? body : JSON.stringify(body)
    });
  },

  put(endpoint, body) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
  },

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  },

  // Auth Operations
  async register(fullName, email, password, phone = null) {
    const res = await this.post('/auth/register', {
      full_name: fullName,
      email,
      password,
      phone
    });
    if (res.access_token) {
      this.setToken(res.access_token);
      this.setUser(res.user);
    }
    return res;
  },

  async login(email, password) {
    const res = await this.post('/auth/login', { email, password });
    if (res.access_token) {
      this.setToken(res.access_token);
      this.setUser(res.user);
    }
    return res;
  },

  async getProfile() {
    const user = await this.get('/auth/me');
    this.setUser(user);
    return user;
  },

  async updateProfile(updates) {
    const user = await this.put('/auth/profile', updates);
    this.setUser(user);
    return user;
  },

  async changePassword(oldPassword, newPassword) {
    return await this.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword
    });
  },

  async forgotPassword(email) {
    return await this.post('/auth/forgot-password', { email });
  },

  async verifyOtp(email, otp) {
    return await this.post('/auth/verify-otp', { email, otp });
  },

  async resetPassword(email, otp, newPassword) {
    return await this.post('/auth/reset-password', {
      email,
      otp,
      new_password: newPassword
    });
  },

  // Medicine & Scan Operations
  async scanMedicinePackage(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.post('/medicine/scan', formData);
  },

  async getScanHistory(limit = 20) {
    return await this.get(`/medicine/scans/history?limit=${limit}`);
  },

  async deleteScanRecord(scanId) {
    return await this.delete(`/medicine/scans/${scanId}`);
  },

  async searchMedicines(query, limit = 5) {
    return await this.get(`/medicine/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  },

  async getSystemInfo() {
    return await this.get('/api');
  }
};

/**
 * Global Toast Notification Helper
 */
function showToast(message, type = 'info', duration = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : type === 'warning' ? '⚠' : 'ℹ';
  toast.innerHTML = `<span style="font-weight:bold; font-size:1.1rem;">${icon}</span> <span>${message}</span>`;

  container.appendChild(toast);

  // Trigger animation
  setTimeout(() => toast.classList.add('show'), 10);

  // Auto remove
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Global export
window.api = api;
window.showToast = showToast;

