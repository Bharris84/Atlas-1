import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run the whole stack: the FastAPI backend with the real
 * financial engine, and the Next.js app against it. Nothing is mocked, because
 * the thing worth testing is that the numbers reach the screen intact.
 *
 * The API runs on its own throwaway SQLite database so a test run never
 * touches development data.
 */
const PYTHON = process.env.ATLAS_PYTHON ?? "../../.venv/bin/python";
const API_PORT = 8123;
const WEB_PORT = 3123;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  reporter: process.env.CI ? "list" : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Some CI images ship a browser already and forbid downloading one.
        // Point PLAYWRIGHT_CHROMIUM_PATH at it there; locally, leave it unset
        // and Playwright uses its own managed browser.
        ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
          : {}),
      },
    },
  ],
  webServer: [
    {
      // The database file is deleted first so each run starts from a known
      // state. It used to be load-bearing for a different reason: before
      // Alembic, create_all() never altered an existing table, so a schema
      // change plus a leftover file failed deep inside a query with "no such
      // column". The API now migrates on startup, so this is hygiene rather
      // than a workaround — but shared state between runs is still worth
      // avoiding.
      command: `rm -f ./atlas-e2e.db && ${PYTHON} -m uvicorn atlas_api.main:app --port ${API_PORT} --app-dir ../api`,
      port: API_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        ATLAS_DATABASE_URL: `sqlite:///./atlas-e2e.db`,
        ENVIRONMENT: "test",
        ATLAS_AI_PROVIDER: "null",
        CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}`,
      },
    },
    {
      // --webpack for the same reason as the build script: Next 16 defaults to
      // Turbopack, which cannot resolve the source-only @atlas/shared-types
      // package entry.
      command: `npx next dev --webpack --port ${WEB_PORT}`,
      port: WEB_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
