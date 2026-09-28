export type User = {
  username: string;
  display_name: string;
  email: string;
  admin: boolean;
};

export type Stats = {
  cpu: number | null;
  ram: number | null;
  gpu: number | null;
  storage: number | null;
  root_disk: number | null;
  bulk_disk: number | null;
  power: number | null;
};

export type Service = {
  name: string;
  container: string;
  url: string;
  description: string;
  state: string;
  status: string;
};

export type ChatMessage = {
  id: number;
  at: string;
  username: string;
  body: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (response.status === 401) {
    const error = new Error("unauthorized");
    (error as Error & { status?: number }).status = 401;
    throw error;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  me: () => request<User>("/api/me"),
  stats: () => request<Stats>("/api/server/stats"),
  services: () => request<{ services: Service[] }>("/api/services"),
  websites: () => request<{ websites: { name: string; url: string; description: string }[] }>("/api/websites"),
  links: () => request<Record<string, string>>("/api/links"),
  chat: () => request<{ messages: ChatMessage[]; retention_days: number }>("/api/chat"),
  sendChat: (body: string) => request<ChatMessage>("/api/chat", { method: "POST", body: JSON.stringify({ body }) }),
  processes: () => request<{ admin: boolean; processes: { name: string; cpu: number; ram_bytes: number }[] }>("/api/processes"),
  audit: () => request<{ events: { id: number; at: string; actor: string; event: string; detail: string }[] }>("/api/audit"),
  referrals: () => request<{ referrals: Record<string, string | number | null>[] }>("/api/referrals"),
  createReferral: (role: string, note: string) =>
    request<{ code: string; signup_url: string }>("/api/referrals", { method: "POST", body: JSON.stringify({ role, note }) }),
  revokeReferral: (code: string) => request("/api/referrals/" + code + "/revoke", { method: "POST" }),
  createAdmin: (payload: { username: string; name: string; email: string; password: string }) =>
    request("/api/admins", { method: "POST", body: JSON.stringify(payload) }),
  action: (name: string) => request<{ ok?: boolean; stopped?: string[]; error?: string; file?: string }>("/api/admin/actions/" + name, { method: "POST" }),
  minecraftStatus: () => request<{ online: boolean; players: string; version: string; detail: string }>("/api/minecraft/status"),
  minecraftLogs: () => request<{ logs: string; error?: string }>("/api/admin/minecraft/logs"),
  llmStatus: () =>
    request<{ model: string | null; configured: boolean; manager_model: string | null; manager_configured: boolean }>("/api/llm/status"),
  llmChat: (messages: { role: string; content: string }[]) =>
    request<{ content: string; compressed: boolean; model: string }>("/api/llm/chat", {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),
  llmManager: (messages: { role: string; content: string }[]) =>
    request<{ content: string; model: string }>("/api/llm/manager", {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
};

export function pct(value: number | null): string {
  return value === null || Number.isNaN(value) ? "n/a" : `${Math.round(value)}%`;
}

export function watts(value: number | null): string {
  return value === null || Number.isNaN(value) ? "n/a" : `${Math.round(value)} W`;
}

export function bytes(value: number): string {
  if (value > 1e9) return `${(value / 1e9).toFixed(1)} GB`;
  if (value > 1e6) return `${(value / 1e6).toFixed(0)} MB`;
  return `${Math.round(value / 1024)} KB`;
}
