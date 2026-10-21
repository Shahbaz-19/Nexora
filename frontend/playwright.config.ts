import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  use: { baseURL: "http://localhost:3000", channel: "msedge", headless: true },
  webServer: {
    command: "npm.cmd run dev -- --port 3000",
    url: "http://localhost:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
