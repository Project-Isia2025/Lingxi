(function () {
  const STORAGE_KEY = "matrix_api_key";

  function storedKey() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch (_e) {
      return "";
    }
  }

  function saveKey(key) {
    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch (_e) {}
  }

  function withKeyHeaders(init) {
    const key = storedKey();
    if (!key) return init || {};
    const opts = init ? Object.assign({}, init) : {};
    const headers = new Headers(opts.headers || {});
    if (!headers.has("X-API-Key")) headers.set("X-API-Key", key);
    opts.headers = headers;
    return opts;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    let response = await nativeFetch(input, withKeyHeaders(init));
    if (response.status !== 401 && response.status !== 403) return response;
    const key = prompt("请输入 API Key（X-API-Key）以继续访问 Dashboard API：");
    if (!key) return response;
    saveKey(key.trim());
    const login = await nativeFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key.trim() }),
    });
    if (!login.ok) return response;
    return nativeFetch(input, withKeyHeaders(init));
  };

  const NativeWS = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    const key = storedKey();
    if (key && typeof url === "string" && !url.includes("api_key=")) {
      const sep = url.includes("?") ? "&" : "?";
      url = url + sep + "api_key=" + encodeURIComponent(key);
    }
    return protocols !== undefined ? new NativeWS(url, protocols) : new NativeWS(url);
  };
  window.WebSocket.prototype = NativeWS.prototype;
  window.WebSocket.CONNECTING = NativeWS.CONNECTING;
  window.WebSocket.OPEN = NativeWS.OPEN;
  window.WebSocket.CLOSING = NativeWS.CLOSING;
  window.WebSocket.CLOSED = NativeWS.CLOSED;
})();
