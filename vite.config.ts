import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Site is served from the GitHub Pages project URL:
// https://melleeyyy.github.io/minisearch/
export default defineConfig({
  plugins: [react()],
  base: "/minisearch/",
  build: { sourcemap: false },
});
