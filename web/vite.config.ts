import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to a local `uvicorn quarry.app:app` on :8000.
// On Vercel the same path is rewritten to the Python function.
export default defineConfig({
  plugins: [react()],
  server: { port: 5176, proxy: { "/api": "http://localhost:8000" } },
});
