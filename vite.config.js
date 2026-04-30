import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.VISUAL_MAS_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  root: "frontend",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
