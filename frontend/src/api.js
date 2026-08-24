const BASE_URL = "http://127.0.0.1:8000";

async function request(path, options) {
  const response = await fetch(`${BASE_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json();
}

export const api = {
  health: () => request("/api/health"),
  sources: () => request("/api/sources"),
  summary: () => request("/api/summary"),
  auditTrail: (filters = {}) => {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== "" && v != null)
    );
    const query = params.toString();
    return request(`/api/audit-trail${query ? `?${query}` : ""}`);
  },
  rerunLayer12: () => request("/api/rerun/layer1-2", { method: "POST" }),
  rerunFull: () => request("/api/rerun/full", { method: "POST" }),
};
