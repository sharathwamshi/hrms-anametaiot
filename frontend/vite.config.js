import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,

    // Allow the dev server to be opened through supported tunnels.
    allowedHosts: [
      ".ngrok-free.app",
      ".ngrok-free.dev",
      ".ngrok.app",
      ".ngrok.io",
      ".trycloudflare.com",
      ".loca.lt",
    ],

    proxy: {
      // Forward API requests to the Flask backend.
      "/api": {
        target: "http://127.0.0.1:5174",
        changeOrigin: true,
      },

      // Forward uploaded and generated files to Flask.
      "/static": {
        target: "http://127.0.0.1:5174",
        changeOrigin: true,
      },
    },
  },
});
