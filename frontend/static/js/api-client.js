/**
 * LightHouse API Client
 * Centralized client for communicating with the backend API
 * Handles JWT authentication, token refresh, and error handling
 */

const API_BASE_URL = 'http://localhost:8000/api';
const STORAGE_KEY_ACCESS = 'lighthouse_access_token';
const STORAGE_KEY_REFRESH = 'lighthouse_refresh_token';
const STORAGE_KEY_USER = 'lighthouse_user';

class LighthouseAPI {
  constructor() {
    this.accessToken = localStorage.getItem(STORAGE_KEY_ACCESS);
    this.refreshToken = localStorage.getItem(STORAGE_KEY_REFRESH);
    this.user = JSON.parse(localStorage.getItem(STORAGE_KEY_USER) || 'null');
  }

  /**
   * Make an authenticated API request
   */
  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      await this.refreshAccessToken();
      if (this.accessToken) {
        headers['Authorization'] = `Bearer ${this.accessToken}`;
        return fetch(url, { ...options, headers });
      } else {
        this.logout();
        throw new Error('Unauthorized');
      }
    }

    return response;
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshAccessToken() {
    if (!this.refreshToken) return false;

    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: this.refreshToken }),
      });

      if (!response.ok) {
        this.logout();
        return false;
      }

      const data = await response.json();
      this.accessToken = data.access;
      localStorage.setItem(STORAGE_KEY_ACCESS, this.accessToken);
      return true;
    } catch (error) {
      this.logout();
      return false;
    }
  }

  /**
   * Register a new user
   */
  async register(email, password, name) {
    const response = await this.request('/auth/register/', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.password?.[0] || error.email?.[0] || 'Registration failed');
    }

    const data = await response.json();
    this.storeTokens(data.refresh, data.access, data.user);
    return data.user;
  }

  /**
   * Login with email and password
   */
  async login(email, password) {
    const response = await this.request('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username: email, password }),
    });

    if (!response.ok) {
      throw new Error('Invalid credentials');
    }

    const data = await response.json();
    this.storeTokens(data.refresh, data.access, data.user);
    return data.user;
  }

  /**
   * Get current user profile
   */
  async getMe() {
    const response = await this.request('/auth/me/');
    if (!response.ok) {
      this.logout();
      throw new Error('Failed to fetch user profile');
    }
    return response.json();
  }

  /**
   * Logout
   */
  logout() {
    this.accessToken = null;
    this.refreshToken = null;
    this.user = null;
    localStorage.removeItem(STORAGE_KEY_ACCESS);
    localStorage.removeItem(STORAGE_KEY_REFRESH);
    localStorage.removeItem(STORAGE_KEY_USER);
  }

  /**
   * Store tokens and user data
   */
  storeTokens(refresh, access, user) {
    this.refreshToken = refresh;
    this.accessToken = access;
    this.user = user;
    localStorage.setItem(STORAGE_KEY_ACCESS, access);
    localStorage.setItem(STORAGE_KEY_REFRESH, refresh);
    localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(user));
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    return !!this.accessToken;
  }

  /**
   * Get all projects
   */
  async getProjects() {
    const response = await this.request('/projects/');
    if (!response.ok) {
      throw new Error('Failed to fetch projects');
    }
    return response.json();
  }

  /**
   * Get a specific project
   */
  async getProject(id) {
    const response = await this.request(`/projects/${id}/`);
    if (!response.ok) {
      throw new Error('Failed to fetch project');
    }
    return response.json();
  }

  /**
   * Get all integrations (tickets)
   */
  async getTickets() {
    const response = await this.request('/tickets/');
    if (!response.ok) {
      throw new Error('Failed to fetch integrations');
    }
    return response.json();
  }

  /**
   * Get all decisions
   */
  async getDecisions() {
    const response = await this.request('/decisions/');
    if (!response.ok) {
      throw new Error('Failed to fetch decisions');
    }
    return response.json();
  }

  /**
   * Get all employees
   */
  async getEmployees() {
    const response = await this.request('/employees/');
    if (!response.ok) {
      throw new Error('Failed to fetch employees');
    }
    return response.json();
  }

  /**
   * Search across all entities
   */
  async search(query) {
    const response = await this.request(`/search/?q=${encodeURIComponent(query)}`);
    if (!response.ok) {
      throw new Error('Search failed');
    }
    return response.json();
  }
}

// Create a singleton instance
const api = new LighthouseAPI();
