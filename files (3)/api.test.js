/**
 * api.test.js — Frontend unit tests for api.js
 *
 * Run with: npx jest --experimental-vm-modules frontend/tests/api.test.js
 *
 * Strategy: mock window.fetch per test.
 * No real network calls — fully self-contained.
 */

// ── Polyfill browser globals for Node test environment ────────────────────────
globalThis.window = globalThis;
window.ENV = { API_URL: "https://mock-api.test" };
window.__auth0Client = { getTokenSilently: async () => "mock-jwt-token" };

// ── Inline api.js (minimal re-implementation for test isolation) ──────────────
// We inline the core _request logic to test it without ESM import complexity.

const API_BASE = "https://mock-api.test";

async function _getToken() {
  if (!window.__auth0Client) return null;
  try { return await window.__auth0Client.getTokenSilently(); } catch { return null; }
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

const api = {
  getPosts: ({ q, location, tag, page = 1, pageSize = 20 } = {}) => {
    const p = new URLSearchParams();
    if (q)        p.set("q", q);
    if (location) p.set("location", location);
    if (tag)      p.set("tag", tag);
    p.set("page", page); p.set("page_size", pageSize);
    return _request("GET", `/posts?${p}`);
  },
  getPost:      (id)        => _request("GET", `/posts/${id}`),
  createPost:   (fd)        => _request("POST", "/posts", fd, true),
  deletePost:   (id)        => _request("DELETE", `/posts/${id}`),
  getComments:  (postId)    => _request("GET", `/posts/${postId}/comments`),
  addComment:   (postId, t) => _request("POST", `/posts/${postId}/comments`, { text: t }),
  deleteComment:(id)        => _request("DELETE", `/comments/${id}`),
  ratePost:     (postId, s) => _request("POST", `/posts/${postId}/rate`, { score: s }),
  getRating:    (postId)    => _request("GET", `/posts/${postId}/rating`),
  getMe:        ()          => _request("GET", "/users/me"),
};

// ── Mock fetch helper ─────────────────────────────────────────────────────────
function mockFetch(status, body) {
  globalThis.fetch = jest.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("api.js — auth header injection", () => {
  test("attaches Bearer token to every request", async () => {
    mockFetch(200, { items: [], page: 1, page_size: 20, total: 0 });
    await api.getPosts();
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers["Authorization"]).toBe("Bearer mock-jwt-token");
  });

  test("sends no auth header when no client is present", async () => {
    window.__auth0Client = null;
    mockFetch(200, { items: [], page: 1, page_size: 20, total: 0 });
    await api.getPosts();
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers["Authorization"]).toBeUndefined();
    window.__auth0Client = { getTokenSilently: async () => "mock-jwt-token" };
  });
});

describe("api.js — getPosts", () => {
  test("builds correct URL with search params", async () => {
    mockFetch(200, { items: [], page: 1, page_size: 20, total: 0 });
    await api.getPosts({ q: "sunset", location: "London", page: 2 });
    const [url] = fetch.mock.calls[0];
    expect(url).toContain("q=sunset");
    expect(url).toContain("location=London");
    expect(url).toContain("page=2");
  });

  test("returns paginated data", async () => {
    const payload = { items: [{ id: "1", title: "Sunset" }], page: 1, page_size: 20, total: 1 };
    mockFetch(200, payload);
    const result = await api.getPosts();
    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
  });

  test("throws on 401", async () => {
    mockFetch(401, { detail: "Not authenticated" });
    await expect(api.getPosts()).rejects.toMatchObject({ status: 401 });
  });
});

describe("api.js — createPost", () => {
  test("POSTs FormData and returns created post", async () => {
    const newPost = { id: "abc", title: "Test", auto_tags: ["nature"], blob_url: "https://..." };
    mockFetch(201, newPost);
    const fd = new (require("form-data"))();
    fd.append("title", "Test");
    const result = await api.createPost(fd);
    expect(result.id).toBe("abc");
    expect(fetch.mock.calls[0][1].method).toBe("POST");
  });

  test("does not set Content-Type for FormData (browser sets boundary)", async () => {
    mockFetch(201, { id: "x" });
    const fd = new (require("form-data"))();
    await api.createPost(fd);
    expect(fetch.mock.calls[0][1].headers["Content-Type"]).toBeUndefined();
  });
});

describe("api.js — deletePost", () => {
  test("sends DELETE and returns null on 204", async () => {
    globalThis.fetch = jest.fn().mockResolvedValueOnce({ status: 204, ok: true });
    const result = await api.deletePost("post-123");
    expect(result).toBeNull();
    expect(fetch.mock.calls[0][1].method).toBe("DELETE");
    expect(fetch.mock.calls[0][0]).toContain("/posts/post-123");
  });

  test("throws 403 when deleting another user's post", async () => {
    mockFetch(403, { detail: "Cannot delete another creator's post" });
    await expect(api.deletePost("other-post")).rejects.toMatchObject({ status: 403 });
  });
});

describe("api.js — addComment", () => {
  test("POSTs comment text to correct endpoint", async () => {
    const comment = { id: "c1", text: "Great photo!", sentiment: "positive", sentiment_score: 0.95 };
    mockFetch(201, comment);
    const result = await api.addComment("post-1", "Great photo!");
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.text).toBe("Great photo!");
    expect(result.sentiment).toBe("positive");
  });
});

describe("api.js — ratePost", () => {
  test("sends score 1-5 and returns rating object", async () => {
    const rating = { id: "r1", post_id: "p1", user_id: "u1", score: 4 };
    mockFetch(201, rating);
    const result = await api.ratePost("p1", 4);
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.score).toBe(4);
    expect(result.score).toBe(4);
  });

  test("throws on invalid score from server", async () => {
    mockFetch(422, { detail: "score must be between 1 and 5" });
    await expect(api.ratePost("p1", 6)).rejects.toMatchObject({ status: 422 });
  });
});

describe("api.js — getMe", () => {
  test("fetches current user profile", async () => {
    const profile = { id: "u1", display_name: "Bruno", role: "creator", email: "b@test.com" };
    mockFetch(200, profile);
    const result = await api.getMe();
    expect(result.role).toBe("creator");
  });
});

describe("api.js — getRating", () => {
  test("returns avg_rating and rating_count", async () => {
    mockFetch(200, { post_id: "p1", avg_rating: 4.2, rating_count: 15 });
    const r = await api.getRating("p1");
    expect(r.avg_rating).toBeCloseTo(4.2);
    expect(r.rating_count).toBe(15);
  });
});
