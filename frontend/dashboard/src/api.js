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
  localStorage.removeItem('biotact_user');
}

/**
 * Get current user info ({id, full_name, ...}) for form prefills.
 * Stored on login; falls back to the JWT `sub` claim (id only) for
 * sessions authenticated before user storage was introduced.
 */
export function getCurrentUser() {
  try {
    const stored = localStorage.getItem('biotact_user');
    if (stored) return JSON.parse(stored);
  } catch {
    // corrupted storage — fall through to the token claim
  }
  const token = getAuthToken();
  if (!token) return null;
  try {
    // base64url → base64; JWT payloads carry no '=' padding, while strict
    // atob() implementations require it — pad to a multiple of 4.
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const payload = JSON.parse(atob(padded));
    const id = Number(payload.sub);
    return Number.isInteger(id) ? { id } : null;
  } catch {
    return null;
  }
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

  if (response.status === 403) {
    throw new Error('Доступ запрещён: требуется роль HR');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  if (response.status === 204) {
    return null;
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
  if (data.user) {
    localStorage.setItem('biotact_user', JSON.stringify(data.user));
  }
  return data;
}

export function isAuthenticated() {
  return !!getAuthToken();
}

/** Change own password (204 on success, 400 if current password is wrong) */
export async function changePassword(currentPassword, newPassword) {
  return apiRequest('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
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

/**
 * Send marketing chat message (AI with function calling)
 * @param {string} message - User message
 * @param {Array|null} history - Chat history [{role, content}]
 * @returns {Promise<{message: string, action: Object|null}>}
 */
export async function marketingChat(message, history = null) {
  const body = { message };
  if (history) {
    body.history = history;
  }

  return apiRequest('/marketing/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ═══════════════════════════════════════════════════════════════
// FILES — Document Storage
// ═══════════════════════════════════════════════════════════════

/** Create a folder */
export async function createFolder(name, parentId = null) {
  const body = { name };
  if (parentId) body.parent_id = parentId;
  return apiRequest('/documents/folders', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** List folders (parentId=null → root) */
export async function listFolders(parentId = null) {
  const query = parentId ? `?parent_id=${parentId}` : '';
  return apiRequest(`/documents/folders${query}`);
}

/** Rename a folder */
export async function renameFolder(folderId, name) {
  return apiRequest(`/documents/folders/${folderId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

/** Delete a folder */
export async function deleteFolder(folderId) {
  return apiRequest(`/documents/folders/${folderId}`, { method: 'DELETE' });
}

/** Upload a file (multipart/form-data) */
export async function uploadFile(file, folderId = null) {
  const token = getAuthToken();
  const formData = new FormData();
  formData.append('file', file);

  const query = folderId ? `?folder_id=${folderId}` : '';
  const response = await fetch(`${API_BASE}/documents/upload${query}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (response.status === 401) { clearAuth(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  return response.json();
}

/** List files (folderId=null → root) */
export async function listFiles(folderId = null) {
  const query = folderId ? `?folder_id=${folderId}` : '';
  return apiRequest(`/documents/${query}`);
}

/** Delete a file */
export async function deleteFile(fileId) {
  return apiRequest(`/documents/${fileId}`, { method: 'DELETE' });
}

/** Get download URL for a file */
export function getFileDownloadUrl(fileId) {
  return `${API_BASE}/documents/${fileId}/download`;
}

/** Download file (triggers browser download) */
export async function downloadFile(fileId, fileName) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/documents/${fileId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}

/** Generate share link */
export async function shareFile(fileId) {
  return apiRequest(`/documents/${fileId}/share`, { method: 'POST' });
}

/** Revoke share link */
export async function unshareFile(fileId) {
  return apiRequest(`/documents/${fileId}/share`, { method: 'DELETE' });
}

/** Get breadcrumbs for a folder */
export async function getBreadcrumbs(folderId) {
  return apiRequest(`/documents/breadcrumbs/${folderId}`);
}

/** Get storage stats */
export async function getFileStats() {
  return apiRequest('/documents/stats');
}

/** Chat about documents (RAG) */
export async function filesChat(message, history = null) {
  const body = { message };
  if (history) body.history = history;
  return apiRequest('/documents/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ═══════════════════════════════════════════════════════════════
// MEDIA — Audio (STT/TTS via OpenAI)
// ═══════════════════════════════════════════════════════════════

/** Transcribe audio file to Russian text */
export async function transcribeAudio(file) {
  const token = getAuthToken();
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/media/audio/transcribe`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (response.status === 401) { clearAuth(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Transcribe failed' }));
    throw new Error(err.detail || 'Transcribe failed');
  }
  return response.json();
}

/** Synthesize Russian text to MP3 audio */
export async function synthesizeAudio(text, voice = 'nova') {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/media/audio/synthesize`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text, voice }),
  });

  if (response.status === 401) { clearAuth(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Synthesize failed' }));
    throw new Error(err.detail || 'Synthesize failed');
  }
  return response.blob();
}

/** List transcriptions (paginated) */
export async function listTranscriptions({ limit = 20, offset = 0 } = {}) {
  return apiRequest(`/media/audio/transcriptions?limit=${limit}&offset=${offset}`);
}

/** Get full transcription detail */
export async function getTranscription(transcriptionId) {
  return apiRequest(`/media/audio/transcriptions/${transcriptionId}`);
}

/** Unified media RAG chat across all knowledge collections */
export async function mediaChat(message, history = null) {
  const body = { message };
  if (history) body.history = history;
  return apiRequest('/media/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Delete transcription (only author) */
export async function deleteTranscription(transcriptionId) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/media/audio/transcriptions/${transcriptionId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) { clearAuth(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Delete failed' }));
    throw new Error(err.detail || 'Delete failed');
  }
}

// ═══════════════════════════════════════════════════════════════
// HR MODULE
// ═══════════════════════════════════════════════════════════════

/** Upload HR template (DOCX/PDF/TXT) */
export async function hrUploadTemplate(file, category) {
  const token = getAuthToken();
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/hr/library?category=${encodeURIComponent(category)}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  return response.json();
}

/** List HR templates */
export async function hrListTemplates(category = null) {
  const params = category ? `?category=${encodeURIComponent(category)}` : '';
  return apiRequest(`/hr/library${params}`);
}

/** Delete HR template */
export async function hrDeleteTemplate(id) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/hr/library/${id}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!response.ok) throw new Error('Delete failed');
  return true;
}

/** HR Chat — send message, get response + optional document */
export async function hrChat(message, history = null) {
  const body = { message };
  if (history) body.history = history;
  return apiRequest('/hr/chat/message', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Download DOCX from text (legacy) */
export async function hrDownloadDocx(text, filename = 'document.docx') {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/hr/documents/download-docx`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text, filename }),
  });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** List generated documents (history) */
export async function hrListDocuments(page = 1, perPage = 20) {
  return apiRequest(`/hr/documents?page=${page}&per_page=${perPage}`);
}

/** Delete generated document */
export async function hrDeleteDocument(id) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/hr/documents/${id}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!response.ok) throw new Error('Delete failed');
}

/** Download rendered DOCX by URL path (from chat) */
export async function hrDownloadRendered(documentUrl) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${documentUrl.replace('/api/v1', '')}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'document.docx';
  a.click();
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════════════════════════
// HR GIFTS — GiftFlow (заявки на подарки)
// Backend: src/biotact/modules/hr/gifts/router.py (/hr/gifts)
// ═══════════════════════════════════════════════════════════════

/** List gift requests with optional filters + pagination */
export async function listGifts({ status, month, year, responsible, page = 1, size = 20 } = {}) {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (month) params.append('month', month);
  if (year) params.append('year', year);
  if (responsible) params.append('responsible', responsible);
  params.append('page', page);
  params.append('size', size);
  return apiRequest(`/hr/gifts?${params.toString()}`);
}

/** Create a gift request */
export async function createGift(data) {
  return apiRequest('/hr/gifts', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** Get a gift request by ID */
export async function getGift(id) {
  return apiRequest(`/hr/gifts/${id}`);
}

/** Partially update a gift request */
export async function updateGift(id, data) {
  return apiRequest(`/hr/gifts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/** Change gift request status (backend appends an audit history record) */
export async function updateGiftStatus(id, { status, comment = null }) {
  return apiRequest(`/hr/gifts/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, comment }),
  });
}

/** Delete a gift request (204 No Content → raw fetch, not apiRequest) */
export async function deleteGift(id) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}/hr/gifts/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) { clearAuth(); throw new Error('Unauthorized'); }
  if (response.status === 403) throw new Error('Доступ запрещён: требуется роль HR');
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Не удалось удалить заявку' }));
    throw new Error(err.detail || 'Не удалось удалить заявку');
  }
}

/** List status history for a gift request */
export async function listGiftHistory(id, { page = 1, size = 20 } = {}) {
  return apiRequest(`/hr/gifts/${id}/history?page=${page}&size=${size}`);
}

// ═══════════════════════════════════════════════════════════════
// HR EVENTS — calendar of employee occasions
// Backend: src/biotact/modules/hr/events/router.py (/hr/events)
// ═══════════════════════════════════════════════════════════════

/** List calendar events with optional filters + pagination */
export async function listEvents({ month, year, department, page = 1, size = 20 } = {}) {
  const params = new URLSearchParams();
  if (month) params.append('month', month);
  if (year) params.append('year', year);
  if (department) params.append('department', department);
  params.append('page', page);
  params.append('size', size);
  return apiRequest(`/hr/events?${params.toString()}`);
}

/** Create a calendar event */
export async function createEvent(data) {
  return apiRequest('/hr/events', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** Get a calendar event by ID */
export async function getEvent(id) {
  return apiRequest(`/hr/events/${id}`);
}

/** Partially update a calendar event */
export async function updateEvent(id, data) {
  return apiRequest(`/hr/events/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/** Delete a calendar event (linked gifts keep living with event_id = NULL) */
export async function deleteEvent(id) {
  return apiRequest(`/hr/events/${id}`, { method: 'DELETE' });
}
