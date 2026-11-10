// Minimal typed client for the WAKALA backend. Read-only in Phase 0.

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { headers: { Accept: "application/json" }, signal });
}

/** POST used only for predefined server-side scenarios (never signs or chooses an agent). */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(`Backend unreachable at ${API_BASE_URL}. Is the API running?`, 0, "NETWORK_ERROR");
  }
  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = res.statusText;
    try {
      const body = (await res.json()) as { error?: { code: string; message: string } };
      if (body.error) ({ code, message } = body.error);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status, code);
  }
  return (await res.json()) as T;
}

// --- Officer console (Phase 4) -------------------------------------------------
// The session token lives only in memory and sessionStorage for this tab. The
// frontend holds NO credentials; the backend derives the officer from the token.
const TOKEN_KEY = "wakala.officer.token";
let officerToken: string | null = (() => {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
})();

export function setOfficerToken(token: string | null): void {
  officerToken = token;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export function hasOfficerToken(): boolean {
  return officerToken !== null;
}

export async function officerRequest<T>(path: string, method: "GET" | "POST" | "DELETE" = "GET", body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (officerToken) headers.Authorization = `Bearer ${officerToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  try {
    return await request<T>(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) setOfficerToken(null);
    throw e;
  }
}
