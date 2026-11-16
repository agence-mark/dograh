// @vitest-environment node
/**
 * [.mark] 502 en production sur `GET /api/v1/tools/?status=…` et `GET /api/v1/credentials/` : Next retirait la barre finale (308), le backend
 * redirigeait (307) vers son adresse interne, le proxy la suivait. Ici : la barre arrive telle quelle au backend, et une redirection du backend
 * n'est jamais suivie, elle est rendue au navigateur en adresse relative.
 */
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { adresseRelative } from '@/lib/adresse-relative';

import { GET } from './route';

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubEnv('BACKEND_URL', 'http://api.railway.internal:8000');
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('proxy /api/v1/[...path]', () => {
  it('garde la barre finale et la requête telles que le client les a écrites', async () => {
    fetchMock.mockResolvedValue(new Response('[]', { status: 200 }));
    await GET(new NextRequest('https://app.exemple.test/api/v1/tools/?status=active,draft'));
    expect(fetchMock.mock.calls[0][0]).toBe('http://api.railway.internal:8000/api/v1/tools/?status=active,draft');
  });

  it('ne suit jamais une redirection du backend : demande manuelle, adresse interne rendue en relatif', async () => {
    fetchMock.mockResolvedValue(
      new Response(null, { status: 307, headers: { location: 'http://api.railway.internal:8000/api/v1/credentials/?a=1' } }),
    );
    const reponse = await GET(new NextRequest('https://app.exemple.test/api/v1/credentials?a=1'));
    expect(fetchMock.mock.calls[0][1].redirect).toBe('manual');
    expect(reponse.status).toBe(307);
    expect(reponse.headers.get('location')).toBe('/api/v1/credentials/?a=1');
  });

  it("laisse telle quelle une redirection qui ne vise pas l'API", () => {
    expect(adresseRelative('https://autre.test/connexion', 'http://api:8000/api/v1/x')).toBe('https://autre.test/connexion');
    expect(adresseRelative('/api/v1/tools/', 'http://api:8000/api/v1/tools')).toBe('/api/v1/tools/');
  });
});
