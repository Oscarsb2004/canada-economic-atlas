import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `public/` already holds the committed bundle (data/), derived renderings
// (media/) and geometry (geo/), all produced by the Python pipeline. Vite
// serves that directory verbatim at the site root, which is the whole reason
// the app needs no loader plumbing: every fetch is a plain path.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: false },
  build: { outDir: "dist", sourcemap: true },
});
