export interface Example {
  question: string;
  evidence: string;
  difficulty: "simple" | "moderate" | "challenging";
}

export interface DatabaseInfo {
  id: string;
  title: string;
  summary: string;
  tables: number;
  columns: number;
  rows: number;
  examples: Example[];
}

export interface Column {
  name: string;
  type: string;
  pk: boolean;
  description: string;
  samples: string[];
}

export interface Schema {
  id: string;
  title: string;
  tables: { name: string; rows: number; columns: Column[] }[];
  foreign_keys: { from: [string, string]; to: [string, string] }[];
}

export interface Chart {
  kind: "stat" | "bar" | "line" | "table";
  label?: string;
  x?: string;
  y?: string;
}

export interface Attempt {
  attempt: number;
  sql: string;
  ok: boolean;
  rows: number;
  model: string;
}

export type AgentEvent =
  | { type: "link"; ms: number; tables: string[]; columns: Record<string, string[]>; values: { table: string; column: string; value: string }[]; schema_tokens: number; total_tables: number }
  | { type: "sql"; attempt: number; sql: string; model: string; ms: number; cache: string | null }
  | { type: "exec"; attempt: number; ok: boolean; error: string | null; rows: number; ms: number }
  | { type: "repair"; attempt: number; reason: string }
  | { type: "result"; sql: string; columns: string[]; rows: (string | number | null)[][]; row_count: number; truncated: boolean; chart: Chart; attempts: Attempt[]; ms: number }
  | { type: "error"; message: string; sql?: string };

export interface Health {
  status: string;
  version: string;
  llm: { endpoint: string; via_sluice: boolean; model: string };
  databases: number;
  max_repairs: number;
  limits: { asks_per_hour: number };
}

export interface Benchmark {
  benchmark: string;
  metric: string;
  n: number;
  overall: { first_attempt: number; final: number };
  by_difficulty: Record<string, { n: number; first_attempt: number; final: number }>;
  by_database: Record<string, { n: number; final: number }>;
  schema_linking_table_recall: number;
  repaired: number;
  broken_by_repair: number;
  avg_attempts: number;
  median_seconds: number;
  providers: Record<string, number>;
}
