import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// Standalone config (the original Replit-workspace config + plugins were stripped).
// Dev server proxies the backend so the frontend can fetch same-origin "/ask".
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/ask": "http://localhost:8000",
    },
  },
});
