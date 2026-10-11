import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": path.resolve(__dirname) } },
  test: { environment: "jsdom", include: ["**/*.test.{ts,tsx}"], exclude: ["node_modules/**", ".next/**"], clearMocks: true },
});
