import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

declare const process: { env: Record<string, string | undefined> };

// `npm run build` writes into the Python package so `uta serve` picks it up.
// `npm run dev` serves on :5173 and proxies the API to a running `uta serve`.
export default defineConfig({
  plugins: [svelte()],
  worker: { format: "es" },
  build: { outDir: "../src/uta/static", emptyOutDir: true, chunkSizeWarningLimit: 2000 },
  server: { proxy: { "/api": process.env.UTA_API ?? "http://127.0.0.1:8000" } },
});
