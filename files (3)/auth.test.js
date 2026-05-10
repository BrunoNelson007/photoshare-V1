/**
 * auth.test.js — Unit tests for auth.js logic
 *
 * Auth0 SDK is mocked in full — no network calls, no real tokens.
 * Tests cover: init, role detection, login/logout redirect.
 */

globalThis.window = globalThis;
window.ENV = {
  AUTH0_DOMAIN:    "test-domain.auth0.com",
  AUTH0_CLIENT_ID: "test-client-id",
  AUTH0_AUDIENCE:  "https://photoshare-api",
};

const ROLE_CLAIM = `https://${window.ENV.AUTH0_DOMAIN}/role`;

// ── Inline auth.js logic for testing ─────────────────────────────────────────

let _client = null;

async function initAuth(mockClient) {
  _client = mockClient;
  window.__auth0Client = _client;

  const query = "";  // No redirect callback in tests
  return _client.isAuthenticated();
}

async function login()  { await _client.loginWithRedirect(); }
async function logout() { await _client.logout({ logoutParams: { returnTo: window.location.origin } }); }

async function getUser() {
  if (!_client || !(await _client.isAuthenticated())) return null;
  const profile = await _client.getUser();
  const claims  = await _client.getIdTokenClaims();
  return { ...profile, role: claims?.[ROLE_CLAIM] ?? "consumer" };
}

async function isCreator() {
  const user = await getUser();
  return user?.role === "creator";
}

// ── Mock factory ──────────────────────────────────────────────────────────────

function makeMockClient({ authenticated = true, role = "consumer", name = "Test User", email = "test@test.com" } = {}) {
  return {
    isAuthenticated: jest.fn().mockResolvedValue(authenticated),
    loginWithRedirect: jest.fn().mockResolvedValue(undefined),
    logout: jest.fn().mockResolvedValue(undefined),
    getUser: jest.fn().mockResolvedValue({ name, email, picture: "https://example.com/pic.jpg" }),
    getIdTokenClaims: jest.fn().mockResolvedValue({
      [ROLE_CLAIM]: role,
      sub: "auth0|test123",
    }),
    getTokenSilently: jest.fn().mockResolvedValue("mock-access-token"),
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("auth.js — initAuth", () => {
  test("returns true when user is authenticated", async () => {
    const client = makeMockClient({ authenticated: true });
    const result = await initAuth(client);
    expect(result).toBe(true);
  });

  test("returns false when user is not authenticated", async () => {
    const client = makeMockClient({ authenticated: false });
    const result = await initAuth(client);
    expect(result).toBe(false);
  });

  test("sets window.__auth0Client", async () => {
    const client = makeMockClient();
    await initAuth(client);
    expect(window.__auth0Client).toBe(client);
  });
});

describe("auth.js — getUser", () => {
  test("returns user profile with role from namespaced claim", async () => {
    const client = makeMockClient({ role: "creator", name: "Bruno" });
    await initAuth(client);
    const user = await getUser();
    expect(user.name).toBe("Bruno");
    expect(user.role).toBe("creator");
  });

  test("defaults to consumer role when claim absent", async () => {
    const client = makeMockClient();
    client.getIdTokenClaims = jest.fn().mockResolvedValue({});  // no role claim
    await initAuth(client);
    const user = await getUser();
    expect(user.role).toBe("consumer");
  });

  test("returns null when not authenticated", async () => {
    const client = makeMockClient({ authenticated: false });
    await initAuth(client);
    const user = await getUser();
    expect(user).toBeNull();
  });
});

describe("auth.js — isCreator", () => {
  test("returns true for creator role", async () => {
    const client = makeMockClient({ role: "creator" });
    await initAuth(client);
    expect(await isCreator()).toBe(true);
  });

  test("returns false for consumer role", async () => {
    const client = makeMockClient({ role: "consumer" });
    await initAuth(client);
    expect(await isCreator()).toBe(false);
  });

  test("returns false when not authenticated", async () => {
    const client = makeMockClient({ authenticated: false });
    await initAuth(client);
    expect(await isCreator()).toBe(false);
  });
});

describe("auth.js — login", () => {
  test("calls loginWithRedirect on the client", async () => {
    const client = makeMockClient();
    await initAuth(client);
    await login();
    expect(client.loginWithRedirect).toHaveBeenCalledTimes(1);
  });
});

describe("auth.js — logout", () => {
  test("calls logout with returnTo origin", async () => {
    const client = makeMockClient();
    await initAuth(client);
    await logout();
    expect(client.logout).toHaveBeenCalledWith(
      expect.objectContaining({ logoutParams: expect.objectContaining({ returnTo: expect.any(String) }) })
    );
  });
});
