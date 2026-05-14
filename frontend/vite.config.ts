import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

const isLan = process.env.VITE_LAN === "1";

export default defineConfig({
  plugins: isLan ? [react(), basicSsl()] : [react()],
  server: {
    https: isLan ? {} : false,
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        secure: false,
      },
      "/audio": {
        target: process.env.VITE_BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
