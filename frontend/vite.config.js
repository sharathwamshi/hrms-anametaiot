import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Allow the dev server to be opened through a tunnel (ngrok etc.) — Vite blocks unknown
    // hosts by default. A leading dot allows the domain and all its subdomains.
    allowedHosts: [".ngrok-free.app", ".ngrok-free.dev", ".ngrok.app", ".ngrok.io", ".trycloudflare.com", ".loca.lt"],
    proxy: {
      "/api": {
        // Use 127.0.0.1 instead of "localhost" — Node 18+ resolves
        // "localhost" to the IPv6 loopback (::1) first, and Flask's dev
        // server doesn't bind IPv6 by default, which causes ECONNREFUSED
        // even though the backend is running fine on IPv4.
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
      // Uploaded/generated files (resumes, job-post images, employee
      // documents) are served by Flask, not Vite. Without this proxy,
      // relative /static/... links resolve against the Vite dev server
      // (5173) instead of the backend (5000) and load a blank page.
      "/static": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
