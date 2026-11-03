import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = new URL("./", import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: /^@\//, replacement: rootDir }],
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
});
