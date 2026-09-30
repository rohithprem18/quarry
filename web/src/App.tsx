import { useEffect } from "react";
import { api } from "./api";
import { Navbar } from "./components/Navbar";
import { useLoad, useRoute } from "./hooks";
import { Ask } from "./views/Ask";
import { Benchmark } from "./views/Benchmark";
import { Schema } from "./views/Schema";

const TITLES = { ask: "Ask", schema: "Schema", benchmark: "Benchmark" };

export default function App() {
  const { route, db, go } = useRoute();
  const [health, healthError] = useLoad((s) => api.health(s), []);
  const [dbs] = useLoad((s) => api.databases(s), []);

  useEffect(() => {
    document.title = `${TITLES[route]} · Quarry`;
  }, [route]);

  return (
    <>
      <Navbar route={route} db={db} health={health} healthError={healthError} />
      <main key={route}>
        {route === "ask" && <Ask dbs={dbs} dbId={db} onDb={(id) => go("ask", id)} health={health} />}
        {route === "schema" && <Schema dbs={dbs} dbId={db} onDb={(id) => go("schema", id)} />}
        {route === "benchmark" && <Benchmark />}
      </main>
    </>
  );
}
