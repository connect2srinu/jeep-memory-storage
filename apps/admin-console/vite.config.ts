import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/control-plane-api": {
          target: environment.CONTROL_PLANE_API_PROXY_TARGET ?? "http://localhost:8080",
          rewrite: (path) => path.replace(/^\/control-plane-api/, ""),
        },
      },
    },
  };
});
