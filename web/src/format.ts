export const fmtInt = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-US"));

export function fmtCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s`;
  return `${Math.round(ms)} ms`;
}

export const fmtPct = (x: number | null | undefined, digits = 0) => (x == null ? "—" : `${(x * 100).toFixed(digits)}%`);

export function fmtAgo(tsSeconds: number, now = Date.now()): string {
  const s = Math.max(0, Math.round(now / 1000 - tsSeconds));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/** "groq/openai/gpt-oss-120b" -> { provider: "groq", model: "gpt-oss-120b" } */
export function splitDeployment(id: string | null | undefined): { provider: string; model: string } {
  if (!id) return { provider: "—", model: "—" };
  const [provider, ...rest] = id.split("/");
  const model = rest.join("/");
  return { provider, model: model.split("/").pop() ?? model };
}

export const PROVIDER_LABEL: Record<string, string> = {
  groq: "Groq",
  gemini: "Gemini",
  openrouter: "OpenRouter",
  cerebras: "Cerebras",
};

export function piiSummary(pii: Record<string, number>): string {
  const parts = Object.entries(pii).map(([k, n]) => `${n} ${k.toLowerCase()}`);
  return parts.length ? parts.join(", ") : "none";
}
