import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:18000",
      "/healthz": "http://127.0.0.1:18000",
    },
  },
  test: { environment: "jsdom" },
});
