import { useEffect, useState } from "react";

export const ROUTES = ["ask", "schema", "benchmark"] as const;
export type Route = (typeof ROUTES)[number];

function parse(): { route: Route; db: string | null } {
  const [path, query] = window.location.hash.replace(/^#\/?/, "").split("?");
  const route = (ROUTES as readonly string[]).includes(path) ? (path as Route) : "ask";
  const db = new URLSearchParams(query ?? "").get("db");
  return { route, db };
}

/** Hash routing with an optional ?db= parameter, so a database choice survives navigation. */
export function useRoute() {
  const [state, setState] = useState(parse);
  useEffect(() => {
    const on = () => setState(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (route: Route, db?: string | null) => {
    window.location.hash = `/${route}${db ? `?db=${db}` : ""}`;
  };
  return { ...state, go };
}

/** Load once; returns [data, error]. */
export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]): [T | null, boolean] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    setError(false);
    load(c.signal)
      .then(setData)
      .catch((e) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) setError(true);
      });
    return () => c.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [data, error];
}
