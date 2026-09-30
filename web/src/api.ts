import type { AgentEvent, Benchmark, DatabaseInfo, Health, Schema } from "./types";

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal });
  if (!r.ok) throw new Error(`${path} returned ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  databases: (signal?: AbortSignal) => getJSON<DatabaseInfo[]>("/api/databases", signal),
  schema: (id: string, signal?: AbortSignal) => getJSON<Schema>(`/api/databases/${id}/schema`, signal),
  benchmark: (signal?: AbortSignal) => getJSON<Benchmark>("/api/benchmark", signal),
  health: (signal?: AbortSignal) => getJSON<Health>("/api/health", signal),

  /** Streams the agent's steps as NDJSON. */
  async ask(body: { db_id: string; question: string; evidence: string }, onEvent: (e: AgentEvent) => void,
            signal?: AbortSignal) {
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!r.ok || !r.body) {
      let message = `Request failed (${r.status})`;
      try {
        message = (await r.json()).error?.message ?? message;
      } catch {
        /* keep default */
      }
      onEvent({ type: "error", message });
      return;
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) onEvent(JSON.parse(line) as AgentEvent);
      }
    }
  },
};
