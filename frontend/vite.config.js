import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// In dev, /api is proxied to the backend so the app and API share one origin
// (same as the nginx setup in production) and no CORS is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_URL || "http://localhost:8000" },
  },
});
