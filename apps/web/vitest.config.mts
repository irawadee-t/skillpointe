import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Vitest config for component tests: the viz2 suite (data-accuracy + a11y for
 * the match-explanation visualizations) and the employer analytics chat
 * (chip re-entry guard + persistence). Run with: pnpm --filter web test
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: [
      "src/components/viz2/__tests__/**/*.test.{ts,tsx}",
      "src/components/employer/__tests__/**/*.test.{ts,tsx}",
      "src/components/ui/__tests__/**/*.test.{ts,tsx}",
      "src/lib/__tests__/**/*.test.{ts,tsx}",
    ],
    setupFiles: ["src/components/viz2/__tests__/setup.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
});
