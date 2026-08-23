import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/memory-api": {
          target: environment.MEMORY_API_PROXY_TARGET ?? "http://localhost:8080",
          rewrite: (path) => path.replace(/^\/memory-api/, ""),
        },
      },
    },
  };
});
