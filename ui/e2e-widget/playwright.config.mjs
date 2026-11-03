// Playwright sur trois moteurs (Chromium, Firefox, WebKit) pour le widget du site, lot S4.
// Aucun site tiers, aucun fournisseur : une page d'essai et une fausse API servies en local (serveur.mjs), des
// reponses enregistrees. Lancer :  cd ui/e2e-widget && npm install && npm run installer-navigateurs && npm test
import { defineConfig, devices } from '@playwright/test';

const PORT = 4777;

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.mjs',
  timeout: 30000,
  retries: 0,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: { command: 'node serveur.mjs', port: PORT, reuseExistingServer: false, env: { PORT: String(PORT) } },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
