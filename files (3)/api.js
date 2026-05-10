/**
 * api.js — PhotoShare REST client
 * All fetch calls go through here so auth headers + error handling are centralised.
 * Tests mock window.fetch to exercise each method in isolation.
 */

const API_BASE = window.ENV?.API_URL || "https://photoshare-api.azurewebsites.net";

/**
 * Retrieve the current Auth0 access token.
 * Expects window.__auth0Client to be set by auth.js after login.
 */
async function _getToken() {
  if (!window.__auth0Client) return null;
  try {
    return await window.__auth0Client.getTokenSilently();
  } catch {
    return null;
  }
}

async function _request(method, path, body = null, isFormData = false) {
  const token = await _getToken();
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!isFormData && body) headers["Content-Type"] = "application/json";

  const opts = { method, headers };
  if (body) opts.body = isFormData ? body : JSON.stringify(body);

  const resp = await fetch(`${API_BASE}${path}`, opts);

  if (resp.status === 204) return null;
  const data = await resp.json();
  if (!resp.ok) throw { status: resp.status, detail: data.detail || "Request failed" };
  return data;
}

// ─── Posts ────────────────────────────────────────────────────────────────────

export async function getPosts({ q, location, tag, page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams();
  if (q)        params.set("q", q);
  if (location) params.set("location", location);
  if (tag)      params.set("tag", tag);
  params.set("page", page);
  params.set("page_size", pageSize);
  return _request("GET", `/posts?${params}`);
}

export async function getPost(id) {
  return _request("GET", `/posts/${id}`);
}

export async function createPost(formData) {
  return _request("POST", "/posts", formData, true);
}

export async function deletePost(id) {
  return _request("DELETE", `/posts/${id}`);
}

// ─── Comments ─────────────────────────────────────────────────────────────────

export async function getComments(postId) {
  return _request("GET", `/posts/${postId}/comments`);
}

export async function addComment(postId, text) {
  return _request("POST", `/posts/${postId}/comments`, { text });
}

export async function deleteComment(commentId) {
  return _request("DELETE", `/comments/${commentId}`);
}

// ─── Ratings ──────────────────────────────────────────────────────────────────

export async function ratePost(postId, score) {
  return _request("POST", `/posts/${postId}/rate`, { score });
}

export async function getRating(postId) {
  return _request("GET", `/posts/${postId}/rating`);
}

// ─── Users ────────────────────────────────────────────────────────────────────

export async function getMe() {
  return _request("GET", "/users/me");
}
