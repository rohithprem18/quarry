import type { Route } from "../hooks";
import type { Health } from "../types";

const LINKS: { route: Route; label: string }[] = [
  { route: "ask", label: "Ask" },
  { route: "schema", label: "Schema" },
  { route: "benchmark", label: "Benchmark" },
];

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="0.5" y="0.5" width="31" height="31" rx="8" fill="none" stroke="rgba(255,255,255,.35)" />
      <path d="M9 10h14v4H9zM9 16h9v6H9z" fill="#fff" />
    </svg>
  );
}

export function Navbar({ route, db, health, healthError }: { route: Route; db: string | null; health: Health | null; healthError: boolean }) {
  const state = healthError ? "bad" : health ? "good" : "warn";
  const label = healthError ? "API offline" : health ? (health.llm.via_sluice ? "LLM via Sluice" : "LLM connected") : "Connecting";
  return (
    <header className="navbar">
      <div className="nav-inner">
        <a className="brand" href="#/ask" aria-label="Quarry home">
          <Logo />
          <span>Quarry</span>
        </a>
        <nav className="nav-links" aria-label="Sections">
          {LINKS.map((l) => (
            <a key={l.route} href={`#/${l.route}${db && l.route !== "benchmark" ? `?db=${db}` : ""}`}
               className={route === l.route ? "active" : undefined} aria-current={route === l.route ? "page" : undefined}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="nav-right">
          <span className={`status ${state}`} role="status">
            <span className="dot" aria-hidden="true" />
            {label}
          </span>
          <a className="pill sm" href="https://github.com/rohithprem18/quarry" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </header>
  );
}
