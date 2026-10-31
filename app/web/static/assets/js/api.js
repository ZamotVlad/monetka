// One door to the backend. In demo mode (GitHub Pages) the same calls go to demo.js.

const params = new URLSearchParams(location.search);
if (params.has("demo")) sessionStorage.setItem("monetka.demo", "1");

export const DEMO =
  location.hostname.endsWith("github.io") || sessionStorage.getItem("monetka.demo") === "1";

const TOKEN = "monetka.token";

export const session = {
  get token() {
    return sessionStorage.getItem(TOKEN);
  },
  save(token) {
    sessionStorage.setItem(TOKEN, token);
  },
  clear() {
    sessionStorage.removeItem(TOKEN);
  },
};

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function send(path, init) {
  if (DEMO) {
    const { demoFetch } = await import("./demo.js");
    return demoFetch(path, init);
  }
  const response = await fetch(`/api/v1${path}`, init);
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  return { status: response.status, data };
}

/**
 * Money-moving calls pass idempotent: true. The key is made once per user action, so if
 * the network drops and we retry, the server sees the same key and does not charge twice.
 */
export async function api(path, { method = "GET", body, headers = {}, idempotent = false, auth = true } = {}) {
  const init = { method, headers: { ...headers } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (auth && session.token) init.headers.Authorization = `Bearer ${session.token}`;
  if (idempotent) init.headers["Idempotency-Key"] = crypto.randomUUID();

  let result;
  for (let attempt = 0; ; attempt++) {
    try {
      result = await send(path, init);
      break;
    } catch (error) {
      if (!idempotent && method !== "GET") throw new ApiError(0, "network", error.message);
      if (attempt === 2) throw new ApiError(0, "network", error.message);
      await new Promise((resolve) => setTimeout(resolve, 400 * 2 ** attempt));
    }
  }

  const { status, data } = result;
  if (status === 401 && auth && session.token) {
    session.clear();
    location.href = "index.html";
  }
  if (status >= 400) {
    const error = data?.error ?? { code: "unknown", message: `HTTP ${status}` };
    throw new ApiError(status, error.code, error.message);
  }
  return data;
}
