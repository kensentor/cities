import { defineConfig } from "vitest/config";

export default defineConfig({
  // Relative asset paths, so the built site/dist works from any static host's sub-path.
  base: "./",
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
