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
