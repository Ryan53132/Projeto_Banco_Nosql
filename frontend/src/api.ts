const API = import.meta.env.VITE_API_URL ?? "/api";

export type Item = {
  id: string;
  name: string;
  description: string;
  done: boolean;
  created_at: string;
  updated_at: string;
};

export type WhoAmI = {
  container: string;
  ip: string;
  zone: string;
  instance_id: string;
};

export type ItemInput = {
  name: string;
  description?: string;
  done?: boolean;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (res.status === 422) throw new Error("Dados inválidos");
    throw new Error(`Erro ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  whoami: () => request<WhoAmI>("/whoami"),

  list: (done?: boolean) =>
    request<Item[]>(done === undefined ? "/items" : `/items?done=${done}`),

  get: (id: string) => request<Item>(`/items/${id}`),

  create: (data: ItemInput) =>
    request<Item>("/items", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: Partial<ItemInput>) =>
    request<Item>(`/items/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  remove: (id: string) => request<void>(`/items/${id}`, { method: "DELETE" }),
};
