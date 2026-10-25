import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/specs',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    trace: 'on-first-retry',
  },
  webServer: {
    command: process.platform === 'win32'
      ? '.venv\\Scripts\\python.exe -m uvicorn src.backend.relay:app --host 127.0.0.1 --port 8000'
      : '.venv/bin/python -m uvicorn src.backend.relay:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/health',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
  projects: [
    {
      name: 'local-mock',
      testMatch: /(01_ui_menu_and_layout|04_drivethru_simulation)\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://127.0.0.1:8000',
        permissions: ['microphone'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
          ],
        },
      },
    },
    {
      name: 'local-relay',
      testMatch: /02_local_relay_websocket\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://127.0.0.1:8000',
      },
    },
    {
      name: 'cloud-live',
      testMatch: /03_cloud_live_agent\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://127.0.0.1:8000',
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
          ],
        },
      },
    },
  ],
});
