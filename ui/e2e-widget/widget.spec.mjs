// Le widget du site sur trois moteurs : chaque etat, micro refuse, plafond atteint, page sans agent.
import { test, expect } from '@playwright/test';

const zone = (page, nom) => page.locator(`[data-zone="${nom}"]`);

test.beforeEach(async ({ page, request }) => {
  await request.get('/__reset');
  // Micro refuse, de facon identique sur les trois moteurs.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: () => Promise.reject(Object.assign(new Error('refuse'), { name: 'NotAllowedError' })) },
    });
  });
});

async function ouvrirEtDemarrer(page) {
  await zone(page, 'rond').click();
  await page.getByRole('dialog').waitFor();
  for (const c of await page.locator('input[type=checkbox]').all()) await c.check();
  await zone(page, 'demarrer').click();
}

test('rond, accroche apres son delai, fenetre, information', async ({ page }) => {
  await page.goto('/essai');
  await expect(zone(page, 'rond')).toBeVisible();
  await expect(zone(page, 'accroche')).toBeVisible({ timeout: 5000 });
  await zone(page, 'accroche').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(zone(page, 'information')).toContainText('assistant virtuel');
  await expect(zone(page, 'demarrer')).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('page sans agent : rien dans la page', async ({ page }) => {
  await page.goto('/essai?site=site_AUCUN');
  await page.waitForTimeout(500);
  await expect(page.locator('[data-mark-widget]')).toHaveCount(0);
});

test('micro refuse : l\'ecrit avec le meme agent, puis l\'avis et le merci', async ({ page }) => {
  await page.goto('/essai');
  await ouvrirEtDemarrer(page);
  await expect(zone(page, 'microRefuse')).toBeVisible();
  await expect(zone(page, 'bulleAgent')).toContainText('Bonjour');
  await page.getByPlaceholder('Écrire un message').fill('Ma référence');
  await zone(page, 'envoyer').click();
  await expect(zone(page, 'bulleVisiteur')).toContainText('Ma référence');
  await zone(page, 'raccrocher').click();
  await page.getByRole('button', { name: '4 étoiles' }).click();
  await zone(page, 'avisEnvoyer').click();
  await expect(zone(page, 'merci')).toBeVisible();
});

test('plafond atteint : les coordonnees partent pour un rappel', async ({ page, request }) => {
  await page.goto('/essai?site=site_PLAFOND');
  await ouvrirEtDemarrer(page);
  await expect(zone(page, 'plafond')).toBeVisible();
  await page.getByPlaceholder('Téléphone ou mail').fill('06 55 55 66 66');
  await zone(page, 'plafondBouton').click();
  await expect(zone(page, 'merci')).toBeVisible();
  const journal = await (await request.get('/__journal')).json();
  expect(journal.some((j) => j.chemin === 'rappel/site_PLAFOND')).toBe(true);
});

test('telephone : la fenetre prend tout l\'ecran', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await page.goto('/essai');
  await zone(page, 'rond').click();
  const boite = await zone(page, 'fenetre').boundingBox();
  expect(Math.round(boite.width)).toBe(390);
  expect(Math.round(boite.height)).toBe(780);
});

test('aucun cookie ni stockage avant le clic', async ({ page, context }) => {
  await page.goto('/essai');
  await expect(zone(page, 'rond')).toBeVisible();
  expect(await context.cookies()).toEqual([]);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});
