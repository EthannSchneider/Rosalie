import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En développement (npm run dev), l'API vient du serveur Python : python bot.py (ou bot.py web)
const api = process.env.ROSALIE_API ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": api } },
  build: { outDir: "dist", emptyOutDir: true },
});
