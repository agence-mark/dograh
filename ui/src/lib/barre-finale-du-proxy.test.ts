// @vitest-environment node
/** [.mark] Garde du 502 de production : Next ne doit pas retirer la barre finale avant le proxy de l'API (le backend déclare `/tools/`, `/credentials/`). */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('next.config.ts', () => {
  it('garde la barre finale des appels vers le backend (skipTrailingSlashRedirect)', () => {
    const source = readFileSync(join(process.cwd(), 'next.config.ts'), 'utf-8');
    expect(source).toMatch(/skipTrailingSlashRedirect:\s*true/);
  });
});
