/**
 * auth.js — Auth0 SPA SDK wrapper
 * Handles login, logout, token management and role detection.
 *
 * Auth0 free tier: 25,000 MAUs — replaces Azure AD B2C.
 * Role is stored as a custom namespaced claim set by an Auth0 Post-Login Action:
 *   https://<your-domain>/role  →  "creator" | "consumer"
 */

const AUTH0_DOMAIN   = window.ENV?.AUTH0_DOMAIN   || "YOUR_DOMAIN.auth0.com";
const AUTH0_CLIENT_ID = window.ENV?.AUTH0_CLIENT_ID || "YOUR_CLIENT_ID";
const AUTH0_AUDIENCE  = window.ENV?.AUTH0_AUDIENCE  || "https://photoshare-api";
const ROLE_CLAIM      = `https://${AUTH0_DOMAIN}/role`;

let _client = null;

/**
 * Initialise the Auth0 client and restore any existing session.
 * Call this once on DOMContentLoaded.
 * @returns {Promise<boolean>} true if the user is already logged in
 */
export async function initAuth() {
  _client = await window.auth0.createAuth0Client({
    domain:   AUTH0_DOMAIN,
    clientId: AUTH0_CLIENT_ID,
    authorizationParams: {
      redirect_uri: window.location.origin,
      audience: AUTH0_AUDIENCE,
      scope: "openid profile email",
    },
    cacheLocation: "memory",   // don't persist tokens in localStorage
    useRefreshTokens: true,
  });

  // Expose globally so api.js can call getTokenSilently()
  window.__auth0Client = _client;

  // Handle redirect callback after login
  const query = window.location.search;
  if (query.includes("code=") && query.includes("state=")) {
    await _client.handleRedirectCallback();
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  return _client.isAuthenticated();
}

/** Redirect to Auth0 Universal Login page. */
export async function login() {
  await _client.loginWithRedirect();
}

/** Log out and redirect back to the home page. */
export async function logout() {
  await _client.logout({ logoutParams: { returnTo: window.location.origin } });
}

/**
 * Return the Auth0 user profile + role claim.
 * @returns {{ name, email, picture, role } | null}
 */
export async function getUser() {
  if (!_client || !(await _client.isAuthenticated())) return null;
  const profile = await _client.getUser();
  const claims  = await _client.getIdTokenClaims();
  return {
    ...profile,
    role: claims?.[ROLE_CLAIM] ?? "consumer",
  };
}

/** Convenience: true if the logged-in user has the "creator" role. */
export async function isCreator() {
  const user = await getUser();
  return user?.role === "creator";
}
