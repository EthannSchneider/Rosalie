// Client de l'API versionnée (/api/v1). La session est un cookie HttpOnly : le navigateur
// l'envoie tout seul, le JavaScript n'y a jamais accès.
export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let unauthorized = () => {};

/** Appelé quand la session a expiré (ou que le compte a été supprimé). */
export function onUnauthorized(callback) {
  unauthorized = callback;
}

export async function request(method, path, body) {
  const init = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") {
    init.headers["Content-Type"] = "application/json"; // exigé par le serveur pour écrire
    if (body !== undefined) init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError(0, "Site injoignable : Rosalie (ou python bot.py web) tourne-t-elle ?");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/session")) unauthorized();
    throw new ApiError(response.status, data.error ?? `erreur ${response.status}`);
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  delete: (path) => request("DELETE", path),
};

export const enc = encodeURIComponent;
