/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
    // La suite completa en paralelo satura la máquina (WSL/CI) y los tests con
    // userEvent superan los 5 s por defecto aunque pasen aislados.
    testTimeout: 30000,
  },
  server: {
    // VITE_HMR=false desactiva el hot-reload (útil al probar streams
    // largos mientras otro agente edita archivos en la misma rama).
    hmr: process.env.VITE_HMR === "false" ? false : undefined,
    allowedHosts: [".tailf19a9b.ts.net", "desktop-ks0esl7.tailf19a9b.ts.net"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
