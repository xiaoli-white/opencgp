import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = new URL("./", import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: /^@\/i18n\//, replacement: `${rootDir}src/i18n/` },
      { find: /^@\//, replacement: rootDir },
    ],
  },
  server: {
    host: "127.0.0.1",
    port: 3001,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 3001,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (
            id.includes("react-markdown") ||
            id.includes("remark") ||
            id.includes("rehype") ||
            id.includes("/unified/") ||
            id.includes("/micromark") ||
            id.includes("/mdast") ||
            id.includes("/hast")
          ) {
            return "markdown";
          }
          if (id.includes("framer-motion") || id.includes("motion-dom") || id.includes("motion-utils")) {
            return "motion";
          }
          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("react-router") ||
            id.includes("/scheduler/")
          ) {
            return "react-vendor";
          }
          return undefined;
        },
      },
    },
  },
});
