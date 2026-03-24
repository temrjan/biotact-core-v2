/**
 * BIOTACT API Client
 * Connects dashboard to FastAPI backend
 */

const API_BASE = window.location.hostname === 'localhost'
  ? 'http://localhost:8000/api/v1'
  : 'https://core.biotact.uz/api/v1';

// Store auth token in memory
let authToken = null;

/**
 * Set authentication token
 */
export function setAuthToken(token) {
  authToken = token;
  localStorage.setItem('biotact_token', token);
}

/**
 * Get stored token
 */
export function getAuthToken() {
  if (!authToken) {
    authToken = localStorage.getItem('biotact_token');
  }
  return authToken;
}

/**
 * Clear authentication
 */
export function clearAuth() {
  authToken = null;
  localStorage.removeItem('biotact_token');
}

/**
 * Make authenticated API request
 */
async function apiRequest(endpoint, options = {}) {
  const token = getAuthToken();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAuth();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// ═══════════════════════════════════════════════════════════════
// AUTH API
// ═══════════════════════════════════════════════════════════════

export async function login(email, password) {
  const data = await apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });

  setAuthToken(data.access_token);
  return data;
}

export function isAuthenticated() {
  return !!getAuthToken();
}

// ═══════════════════════════════════════════════════════════════
// DASHBOARD API
// ═══════════════════════════════════════════════════════════════

/**
 * Get KPI data (revenue, expenses, profit, margin)
 */
export async function getKPI(startDate, endDate) {
  let query = '';
  if (startDate || endDate) {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    query = `?${params.toString()}`;
  }

  return apiRequest(`/dashboard/kpi${query}`);
}

/**
 * Get financial report
 */
export async function getReport(startDate, endDate) {
  let query = '';
  if (startDate || endDate) {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    query = `?${params.toString()}`;
  }

  return apiRequest(`/dashboard/report${query}`);
}

/**
 * Get transactions list
 */
export async function getTransactions(options = {}) {
  const params = new URLSearchParams();

  if (options.startDate) params.append('start_date', options.startDate);
  if (options.endDate) params.append('end_date', options.endDate);
  if (options.category) params.append('category', options.category);
  if (options.type) params.append('type', options.type);
  if (options.limit) params.append('limit', options.limit);
  if (options.offset) params.append('offset', options.offset);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest(`/dashboard/transactions${query}`);
}

/**
 * Create new transaction
 */
export async function createTransaction(data) {
  return apiRequest('/dashboard/transactions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Delete transaction
 */
export async function deleteTransaction(transactionId) {
  return apiRequest(`/dashboard/transactions/${transactionId}`, {
    method: 'DELETE',
  });
}

// ═══════════════════════════════════════════════════════════════
// CHAT API (Function Calling)
// ═══════════════════════════════════════════════════════════════

/**
 * Send chat message to AI
 * For dashboard department, uses Function Calling to parse commands
 */
export async function sendChatMessage(message, sessionId = null) {
  const body = { message };
  if (sessionId) {
    body.session_id = sessionId;
  }

  return apiRequest('/chat/query', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Get chat sessions
 */
export async function getChatSessions(limit = 20, offset = 0) {
  return apiRequest(`/chat/sessions?limit=${limit}&offset=${offset}`);
}

// ═══════════════════════════════════════════════════════════════
// HEALTH CHECK
// ═══════════════════════════════════════════════════════════════

export async function healthCheck() {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}

// ═══════════════════════════════════════════════════════════════
// PROMPTS API
// ═══════════════════════════════════════════════════════════════

/**
 * Get prompt by name
 */
export async function getPrompt(name) {
  return apiRequest(`/prompts/${name}`);
}

/**
 * Update prompt content
 */
export async function updatePrompt(name, content) {
  return apiRequest(`/prompts/${name}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

/**
 * List all prompts
 */
export async function listPrompts() {
  return apiRequest('/prompts/');
}

// ═══════════════════════════════════════════════════════════════
// MARKETING — Content Generation
// ═══════════════════════════════════════════════════════════════

/**
 * Generate 2 post variants for a BIOTACT product
 * @param {string} product - Product name
 * @param {string|null} context - Optional context (audience, season, trend)
 * @returns {Promise<{variants: Array, model_used: string, error: string|null}>}
 */
export async function generateContent(product, context = null) {
  const body = { product };
  if (context) {
    body.context = context;
  }

  return apiRequest('/marketing/generate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Get content generation history
 * @param {Object} options - Filter options
 * @param {string|null} options.product - Filter by product name
 * @param {number|null} options.days - Filter by last N days
 * @param {number} options.limit - Max results (default 50)
 * @returns {Promise<Array>}
 */
export async function getContentHistory({ product, days, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (product) params.append('product', product);
  if (days) params.append('days', days);
  if (limit) params.append('limit', limit);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest(`/marketing/history${query}`);
}
