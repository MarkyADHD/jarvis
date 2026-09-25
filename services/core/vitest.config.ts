import { defineConfig } from "vitest/config";

// Without this, vitest also picks up the compiled *.test.js files under
// dist/ once the package has been built, running every test twice.
export default defineConfig({
  test: {
    exclude: ["**/node_modules/**", "**/dist/**"],
  },
});
