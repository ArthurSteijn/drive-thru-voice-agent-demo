import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws/voice": {
        target: "ws://localhost:8000",
        ws: true,
      },
      "/health": {
        target: "http://localhost:8000",
      },
    },
  },
});
