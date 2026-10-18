const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";
export async function api(path, method = "GET", body) {
  const res = await fetch(BASE + path, {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} failed (${res.status})`);
  return res.json();
}
