(function () {
  const config = window.KAIZO_AUTH_CONFIG || {};
  window.KAIZO_AUTH_READY = (async function () {
    try {
      if (!config.clientId) throw new Error("AUTH0_SPA_CLIENT_ID_REQUIRED: set the public clientId in frontend/auth-config.js and allow this site origin in Auth0 callback/web-origin settings.");
      if (typeof window.createAuth0Client !== "function") throw new Error("AUTH0_SDK_UNAVAILABLE: Auth0 SPA SDK did not load. " + (window.KAIZO_AUTH_SDK_LOAD_ERROR || "No SDK loader diagnostic is available."));
      const client = await window.createAuth0Client({
        domain: config.domain,
        clientId: config.clientId,
        authorizationParams: { audience: config.audience, redirect_uri: window.location.origin }
      });
      if (window.location.search.includes("code=") && window.location.search.includes("state=")) {
        await client.handleRedirectCallback();
        window.history.replaceState({}, document.title, window.location.pathname);
      }
      window.KAIZO_AUTH = {
        getAccessTokenSilently: () => client.getTokenSilently(),
        loginWithRedirect: () => client.loginWithRedirect({ authorizationParams: { audience: config.audience, redirect_uri: window.location.origin } }),
        isAuthenticated: () => client.isAuthenticated()
      };
      return window.KAIZO_AUTH;
    } catch (error) {
      window.KAIZO_AUTH_INIT_ERROR = String(error && error.message ? error.message : error);
      return null;
    }
  })();
})();
