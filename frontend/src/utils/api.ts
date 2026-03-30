/**
 * Generic fetch wrapper for backend API calls. Prepends /api to all paths,
 * sets JSON content-type, and throws on non-OK responses with the error detail.
 *
 * Used by ProfilePage and PeoplePage for direct REST calls. The chat hook
 * uses its own fetch (postChat) because it needs slightly different handling.
 */
const BASE_URL = "/api";

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}
