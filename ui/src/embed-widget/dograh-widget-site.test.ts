/**
 * [.mark] U10 / lot S4 : le widget du site (public/embed/dograh-widget.js), joué dans jsdom avec des réponses
 * enregistrées en fichier de test : aucune requête réelle, aucun site tiers.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | ancien script | une adresse ?token= charge le script historique, même adresse, mêmes attributs data-* |
 * | page sans agent | config « inactif » : rien dans la page, aucun compteur |
 * | confidentialité | aucun cookie, aucun stockage ; toutes les requêtes sans identifiants ; polices de chez nous seulement |
 * | rond et accroche | rond nommé ; accroche telle que saisie (retours à la ligne), après son délai, fermable |
 * | information et cases | l'annonce IA, les deux cases, démarrer grisé tant qu'elles ne sont pas cochées ; compteur « ouvert » |
 * | micro refusé | la même session passe à l'écrit (mode écrit), on écrit, on raccroche, l'avis suit |
 * | voix | la signalisation part avec l'agent et la conversation ; la fin de l'appel ouvre l'avis |
 * | plafond | refus du mois ou de l'adresse : « laissez vos coordonnées », la demande de rappel part avec la clé du site |
 * | avis | étoiles, questions selon la note, cases, rappel avec coordonnées ; réessaie tant que la conversation n'est pas finie |
 * | accessibilité | dialogue nommé, boutons nommés, Échap, focus |
 * | aperçu | le même rendu dans un cadre du portail, sans requête, repères data-zone présents |
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'public/embed/dograh-widget.js'), 'utf8');

const API = 'http://api.test';
const SCRIPT = `http://widget.test/embed/dograh-widget.js?site=site_CLE&apiEndpoint=${encodeURIComponent(API)}`;

type Appel = { url: string; init?: RequestInit; corps?: any };
type W = Window & { MarkWidget?: any };

const CONFIG = {
    actif: true,
    token: 'emb_TOKEN',
    widget_type: 'voice',
    apparence: {},
    couleurs: {},
    turn_enabled: false,
    force_turn_relay: false,
};

function reponse(corps: unknown, statut = 200) {
    return { ok: statut >= 200 && statut < 300, status: statut, json: async () => corps } as Response;
}

/** Un faux serveur : une table « adresse → réponse » ; chaque appel est noté. */
function serveur(routes: Record<string, (appel: Appel) => Response | Promise<Response>>) {
    const appels: Appel[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const appel: Appel = { url, init, corps: init?.body ? JSON.parse(String(init.body)) : undefined };
        appels.push(appel);
        for (const [motif, repondre] of Object.entries(routes)) {
            if (url.includes(motif)) return repondre(appel);
        }
        return reponse({ detail: 'inconnu' }, 404);
    });
    return { appels, fetchMock };
}

async function attendre(ms = 0) {
    if (ms > 0) await vi.advanceTimersByTimeAsync(ms);
    for (let i = 0; i < 8; i += 1) await vi.advanceTimersByTimeAsync(0);
}

function racine(): ShadowRoot {
    const hote = document.querySelector('[data-mark-widget]') as HTMLElement | null;
    expect(hote).not.toBeNull();
    return hote!.shadowRoot as ShadowRoot;
}
const zone = (nom: string) => racine().querySelector(`[data-zone="${nom}"]`) as HTMLElement | null;

async function charger(fetchMock: ReturnType<typeof vi.fn>, scriptSrc = SCRIPT, attributs = '') {
    vi.stubGlobal('fetch', fetchMock);
    document.head.innerHTML = '';
    document.body.innerHTML = `<script src="${scriptSrc}" ${attributs}></script>`;
    delete (window as W).MarkWidget;
    window.eval(source);
    await attendre();
}

beforeEach(() => {
    vi.useFakeTimers();
    window.history.replaceState({}, '', '/tarifs?utm=secret#haut');
});
afterEach(() => {
    (window as W).MarkWidget?.instance?.()?.detruire();
    delete (window as W).MarkWidget;
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.head.innerHTML = '';
    document.body.innerHTML = '';
});

describe('le script par jeton', () => {
    it('charge le script historique avec la même adresse et les mêmes attributs, sans toucher au réseau', async () => {
        const { fetchMock } = serveur({});
        await charger(
            fetchMock,
            'http://widget.test/embed/dograh-widget.js?token=emb_TEST&apiEndpoint=api.test',
            `data-dograh-context='{"a":"b"}'`,
        );
        const injecte = document.head.querySelector('script') as HTMLScriptElement;
        expect(injecte.src).toBe('http://widget.test/embed/dograh-widget-jeton.js?token=emb_TEST&apiEndpoint=api.test');
        expect(injecte.getAttribute('data-dograh-context')).toBe('{"a":"b"}');
        expect(fetchMock).not.toHaveBeenCalled();
        expect(document.querySelector('[data-mark-widget]')).toBeNull();
    });

    it('le fichier historique existe et porte toujours son interface', () => {
        const historique = readFileSync(resolve(process.cwd(), 'public/embed/dograh-widget-jeton.js'), 'utf8');
        expect(historique).toContain('window.DograhWidget = {');
        expect(historique).toContain("scriptUrl.searchParams.get('token')");
    });
});

describe('une page sans agent', () => {
    it("n'affiche rien et ne compte rien", async () => {
        const { appels, fetchMock } = serveur({ '/site/site_CLE/config': () => reponse({ actif: false }) });
        await charger(fetchMock);
        expect(document.querySelector('[data-mark-widget]')).toBeNull();
        expect(appels.map((a) => a.url)).toEqual([`${API}/api/v1/public/embed/site/site_CLE/config?chemin=%2Ftarifs`]);
    });

    it('config en erreur : la page du client reste intacte', async () => {
        const { fetchMock } = serveur({ '/config': () => reponse({ detail: 'non' }, 403) });
        await charger(fetchMock);
        expect(document.querySelector('[data-mark-widget]')).toBeNull();
    });
});

describe('confidentialité', () => {
    it('ni cookie ni stockage, requêtes sans identifiants, polices de chez nous', async () => {
        const polices: string[] = [];
        class FauxFontFace {
            constructor(_nom: string, source: string) {
                polices.push(source);
            }
            load() {
                return Promise.resolve(this);
            }
        }
        vi.stubGlobal('FontFace', FauxFontFace);
        Object.defineProperty(document, 'fonts', { value: { add: vi.fn() }, configurable: true });
        const setItem = vi.spyOn(Storage.prototype, 'setItem');
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
        });
        await charger(fetchMock);
        expect(document.cookie).toBe('');
        expect(setItem).not.toHaveBeenCalled();
        expect(window.localStorage.length).toBe(0);
        expect(window.sessionStorage.length).toBe(0);
        expect(appels.length).toBeGreaterThan(0);
        for (const a of appels) expect(a.init?.credentials).toBe('omit');
        expect(polices.length).toBeGreaterThan(0);
        for (const p of polices) {
            expect(p).toContain('http://widget.test/embed/fonts/Switzer-');
            expect(p).not.toMatch(/googleapis|gstatic|fonts\.google/);
        }
        expect(source).not.toMatch(/fonts\.googleapis|fonts\.gstatic/);
    });

    it("le contexte de la page ne porte que le chemin (jamais les paramètres ni l'ancre)", async () => {
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/init': () => reponse({ detail: { code: 'x' } }, 500),
        });
        await charger(fetchMock);
        zone('rond')!.click();
        await attendre();
        const cases = racine().querySelectorAll('input[type=checkbox]') as NodeListOf<HTMLInputElement>;
        cases.forEach((c) => c.click());
        (zone('demarrer') as HTMLButtonElement).click();
        await attendre();
        const init = appels.find((a) => a.url.endsWith('/public/embed/init'));
        expect(init?.corps.context_variables.page_url).toBe('http://localhost:3000/tarifs');
        expect(JSON.stringify(init?.corps)).not.toContain('secret');
    });
});

describe('le rond et son accroche', () => {
    it('le rond est un bouton nommé, ancré à droite, et compte son affichage', async () => {
        const { appels, fetchMock } = serveur({ '/config': () => reponse(CONFIG), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        const rond = zone('rond')!;
        expect(rond.tagName).toBe('BUTTON');
        expect(rond.getAttribute('aria-label')).toBe('Une question ? Parlez-moi.');
        const evenement = appels.find((a) => a.url.endsWith('/evenement'));
        expect(evenement?.corps).toEqual({ evenement: 'affiche', chemin: '/tarifs', cle: 'site_CLE' });
        // Sans WebGL (jsdom) : un disque de la couleur, rien d'animé.
        expect(rond.querySelector('canvas')).toBeNull();
    });

    it("l'accroche apparaît après son délai, tel que saisie, et se ferme", async () => {
        const config = {
            ...CONFIG,
            apparence: { declenchement: 'delai', delai_s: 3, textes: { accroche: 'Bonjour\nUne question ?\nParlez-moi' } },
        };
        const { fetchMock } = serveur({ '/config': () => reponse(config), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        expect(zone('accroche')).toBeNull();
        await attendre(1000);
        expect(zone('accroche')).toBeNull();
        await attendre(2500);
        const carte = zone('accroche')!;
        expect(carte.textContent).toBe('Bonjour\nUne question ?\nParlez-moi'); // retours à la ligne gardés, aucun ajouté
        expect(carte.style.whiteSpace).toBe('pre-wrap');
        expect(carte.style.width).toBe('max-content');
        (racine().querySelector('.mk-x') as HTMLButtonElement).click();
        expect(zone('accroche')).toBeNull();
        expect(zone('rond')).not.toBeNull();
        await attendre(10000);
        expect(zone('accroche')).toBeNull(); // fermée, elle ne revient pas
    });

    it('au survol (déclenchement par clic), le rond montre l’accroche', async () => {
        const { fetchMock } = serveur({ '/config': () => reponse(CONFIG), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        zone('rond')!.dispatchEvent(new MouseEvent('mouseenter'));
        expect(zone('accroche')?.textContent).toBe('Une question ?\nParlez-moi.');
    });

    it('à gauche quand le client le règle', async () => {
        const config = { ...CONFIG, apparence: { position: 'bas-gauche' } };
        const { fetchMock } = serveur({ '/config': () => reponse(config), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        expect((racine().querySelector('.mk-ancre') as HTMLElement).style.left).toBe('20px');
    });
});

describe('information et cases', () => {
    it("l'annonce IA, la mention .mark, les deux cases, démarrer grisé jusqu'aux deux coches", async () => {
        const config = { ...CONFIG, apparence: { lien_confidentialite: 'https://client.fr/confidentialite' } };
        const { appels, fetchMock } = serveur({ '/config': () => reponse(config), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        zone('rond')!.click();
        await attendre();
        expect(zone('information')?.textContent).toContain('assistant virtuel');
        expect(racine().textContent).toContain('Assistant IA conçu par .mark');
        const lien = racine().querySelector('a[href="https://client.fr/confidentialite"]') as HTMLAnchorElement;
        expect(lien.rel).toContain('noopener');
        const demarrer = zone('demarrer') as HTMLButtonElement;
        expect(demarrer.disabled).toBe(true);
        const cases = racine().querySelectorAll('input[type=checkbox]') as NodeListOf<HTMLInputElement>;
        expect(cases.length).toBe(2);
        cases[0].click();
        expect((zone('demarrer') as HTMLButtonElement).disabled).toBe(true);
        cases[1].click();
        expect((zone('demarrer') as HTMLButtonElement).disabled).toBe(false);
        expect(appels.filter((a) => a.corps?.evenement === 'ouvert')).toHaveLength(1);
        expect(appels.find((a) => a.url.endsWith('/init'))).toBeUndefined(); // rien ne part avant « démarrer »
    });
});

describe('accessibilité', () => {
    it('dialogue nommé, boutons nommés, Échap ferme, le focus entre dans la fenêtre', async () => {
        const { fetchMock } = serveur({ '/config': () => reponse(CONFIG), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        zone('rond')!.click();
        await attendre();
        const fenetre = zone('fenetre')!;
        expect(fenetre.getAttribute('role')).toBe('dialog');
        expect(fenetre.getAttribute('aria-label')).toBeTruthy();
        for (const b of Array.from(racine().querySelectorAll('button')) as HTMLButtonElement[]) {
            expect((b.textContent || '').trim() || b.getAttribute('aria-label')).toBeTruthy();
        }
        expect(racine().activeElement).not.toBeNull();
        fenetre.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        expect(zone('fenetre')).toBeNull();
        expect(zone('rond')).not.toBeNull();
    });

    it('le texte des boutons reste lisible : noir ou blanc selon la couleur du bouton', async () => {
        const config = { ...CONFIG, apparence: { couleur_base: '#ffe14d' }, couleurs: { boutons: '#ffe14d' } };
        const { fetchMock } = serveur({ '/config': () => reponse(config), '/evenement': () => reponse({ ok: true }) });
        await charger(fetchMock);
        zone('rond')!.click();
        await attendre();
        expect((zone('demarrer') as HTMLElement).style.color).toBe('rgb(17, 17, 17)'); // #111111, la règle du serveur
    });
});

async function jusquaLaConversation() {
    zone('rond')!.click();
    await attendre();
    (racine().querySelectorAll('input[type=checkbox]') as NodeListOf<HTMLInputElement>).forEach((c) => c.click());
    (zone('demarrer') as HTMLButtonElement).click();
    await attendre();
}

describe("micro refusé : l'écrit avec le même agent", () => {
    it('la session passe à l’écrit, on écrit, on raccroche, l’avis suit', async () => {
        const tour = (id: string, u: string | null, a: string) => ({
            id, status: 'completed', user_message: u ? { text: u } : null, assistant_message: { text: a },
        });
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () =>
                reponse({
                    session_token: 'emb_session_ECRIT', workflow_run_id: 5, config: { workflow_id: 9 }, widget_type: 'chat',
                    chat_session: { revision: 2, state: 'running', is_completed: false, turns: [tour('t1', null, 'Bonjour, je vous écoute.')] },
                }),
            '/chat/emb_session_ECRIT/messages': () =>
                reponse({
                    revision: 4, state: 'running', is_completed: false,
                    turns: [tour('t1', null, 'Bonjour, je vous écoute.'), tour('t2', 'Mon numéro de commande', 'Merci, c’est noté.')],
                }),
            '/chat/emb_session_ECRIT/end': () => reponse({ revision: 5, state: 'completed', is_completed: true, turns: [] }),
        });
        // Aucun micro : jsdom n'a ni mediaDevices ni RTCPeerConnection.
        await charger(fetchMock);
        await jusquaLaConversation();
        const init = appels.find((a) => a.url.endsWith('/public/embed/init'))!;
        expect(init.corps.mode).toBe('ecrit');
        expect(init.corps.token).toBe('emb_TOKEN');
        expect(zone('microRefuse')?.textContent).toBe("Le micro n’est pas disponible. Vous pouvez m’écrire.");
        expect(zone('bulleAgent')?.textContent).toBe('Bonjour, je vous écoute.');
        expect(zone('raccrocher')?.getAttribute('aria-label')).toBe('Raccrocher');
        const champ = racine().querySelector('.mk-champ input') as HTMLInputElement;
        expect(champ.getAttribute('aria-label')).toBe('Écrire un message');
        champ.value = 'Mon numéro de commande';
        (zone('envoyer') as HTMLButtonElement).click();
        await attendre();
        const message = appels.find((a) => a.url.endsWith('/chat/emb_session_ECRIT/messages'))!;
        expect(message.corps).toEqual({ text: 'Mon numéro de commande', expected_revision: 2 });
        expect(Array.from(racine().querySelectorAll('[data-zone="bulleVisiteur"]')).map((n) => n.textContent)).toEqual(['Mon numéro de commande']);
        (zone('raccrocher') as HTMLButtonElement).click();
        await attendre();
        const fin = appels.find((a) => a.url.endsWith('/chat/emb_session_ECRIT/end'))!;
        expect(fin.corps).toEqual({ expected_revision: 4 });
        expect(zone('etoiles')).not.toBeNull(); // l'avis
    });

    it('un texte reçu ne devient jamais du HTML', async () => {
        const { fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () =>
                reponse({
                    session_token: 's', workflow_run_id: 1, config: { workflow_id: 1 }, widget_type: 'chat',
                    chat_session: { revision: 1, state: 'running', is_completed: false,
                        turns: [{ id: 'a', status: 'completed', assistant_message: { text: '<img src=x onerror=alert(1)>' } }] },
                }),
        });
        await charger(fetchMock);
        await jusquaLaConversation();
        expect(racine().querySelector('img')).toBeNull();
        expect(zone('bulleAgent')?.textContent).toBe('<img src=x onerror=alert(1)>');
    });
});

describe('la voix', () => {
    it("envoie la signalisation avec l'agent et la conversation, et la fin de l'appel ouvre l'avis", async () => {
        const envoyes: any[] = [];
        let ws: any = null;
        class FauxWebSocket {
            readyState = 0;
            onopen: any; onmessage: any; onclose: any; onerror: any;
            constructor(public url: string) {
                ws = this;
                setTimeout(() => { this.readyState = 1; this.onopen?.(); }, 0);
            }
            send(m: string) { envoyes.push(JSON.parse(m)); }
            close() { this.readyState = 3; }
        }
        let pc: any = null;
        class FauxPeer {
            connectionState = 'new';
            onconnectionstatechange: any; ontrack: any; onicecandidate: any;
            constructor(public config: any) { pc = this; }
            addTrack() {}
            async createOffer() { return { type: 'offer', sdp: 'v=0' }; }
            async setLocalDescription() {}
            async setRemoteDescription() { this.connectionState = 'connected'; this.onconnectionstatechange?.(); }
            close() { this.connectionState = 'closed'; }
        }
        const piste = { stop: vi.fn(), enabled: true };
        vi.stubGlobal('WebSocket', FauxWebSocket);
        vi.stubGlobal('RTCPeerConnection', FauxPeer);
        Object.defineProperty(navigator, 'mediaDevices', {
            configurable: true,
            value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [piste], getAudioTracks: () => [piste] })) },
        });
        const { appels, fetchMock } = serveur({
            '/config': () => reponse({ ...CONFIG, turn_enabled: false }),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () =>
                reponse({ session_token: 'emb_session_VOIX', workflow_run_id: 77, config: { workflow_id: 9 }, widget_type: 'voice' }),
        });
        await charger(fetchMock);
        await jusquaLaConversation();
        expect(appels.find((a) => a.url.endsWith('/public/embed/init'))!.corps.mode).toBeUndefined();
        expect(ws.url).toBe('ws://api.test/api/v1/ws/public/signaling/emb_session_VOIX');
        const offre = envoyes.find((m) => m.type === 'offer');
        expect(offre.payload).toMatchObject({ workflow_id: 9, workflow_run_id: 77, type: 'offer' });
        expect(pc.config.iceServers).toEqual([{ urls: ['stun:stun.l.google.com:19302'] }]);
        // La réponse du serveur : la connexion monte, l'orbe écoute.
        await ws.onmessage({ data: JSON.stringify({ type: 'answer', payload: { sdp: 'v=0' } }) });
        await attendre();
        expect(racine().querySelector('[data-etat]')?.textContent).toBe('Je vous écoute');
        // Couper le micro.
        const micro = racine().querySelector('button[aria-label="Couper le micro"]') as HTMLButtonElement;
        micro.click();
        expect(piste.enabled).toBe(false);
        expect(racine().querySelector('button[aria-label="Rétablir le micro"]')?.getAttribute('aria-pressed')).toBe('true');
        // S5 : le visiteur écrit pendant l'appel ; le texte part sur la signalisation, un refus le rend au champ.
        const champ = racine().querySelector('[data-zone="saisieVoix"] input') as HTMLInputElement;
        champ.value = '  Dupont, 06 12 34 56 78  ';
        (racine().querySelector('[data-zone="envoyerVoix"]') as HTMLButtonElement).click();
        expect(envoyes.find((m) => m.type === 'texte-visiteur')?.payload).toEqual({ texte: 'Dupont, 06 12 34 56 78' });
        expect(champ.value).toBe('');
        await ws.onmessage({ data: JSON.stringify({ type: 'texte-visiteur-resultat', payload: { ok: false, code: 'trop_rapide' } }) });
        expect(champ.value).toBe('Dupont, 06 12 34 56 78');
        // L'agent raccroche.
        await ws.onmessage({ data: JSON.stringify({ type: 'call-ended', payload: {} }) });
        await attendre();
        expect(zone('etoiles')).not.toBeNull();
        expect(piste.stop).toHaveBeenCalled();
    });

    it('voix impossible (connexion qui échoue) : le même agent, à l’écrit', async () => {
        class FauxWebSocket {
            readyState = 1; onopen: any; onerror: any;
            constructor() { setTimeout(() => this.onerror?.(new Error('x')), 0); }
            send() {}
            close() {}
        }
        class FauxPeer {
            onconnectionstatechange: any;
            addTrack() {}
            close() {}
        }
        vi.stubGlobal('WebSocket', FauxWebSocket);
        vi.stubGlobal('RTCPeerConnection', FauxPeer);
        const piste = { stop: vi.fn(), enabled: true };
        Object.defineProperty(navigator, 'mediaDevices', {
            configurable: true,
            value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [piste], getAudioTracks: () => [piste] })) },
        });
        let n = 0;
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () => {
                n += 1;
                return n === 1
                    ? reponse({ session_token: 'v', workflow_run_id: 1, config: { workflow_id: 1 }, widget_type: 'voice' })
                    : reponse({ session_token: 'e', workflow_run_id: 2, config: { workflow_id: 1 }, widget_type: 'chat',
                        chat_session: { revision: 1, state: 'running', is_completed: false, turns: [] } });
            },
        });
        await charger(fetchMock);
        await jusquaLaConversation();
        await attendre(100);
        const inits = appels.filter((a) => a.url.endsWith('/public/embed/init'));
        expect(inits.map((a) => a.corps.mode)).toEqual([undefined, 'ecrit']);
        expect(zone('microRefuse')).not.toBeNull();
        expect(piste.stop).toHaveBeenCalled();
    });
});

describe('le plafond atteint', () => {
  for (const code of ['monthly_cap_reached', 'address_rate_limited']) {
    it(`${code} : coordonnées, puis la demande de rappel part avec la clé du site`, async () => {
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () => reponse({ detail: { code, message: 'x' } }, code === 'monthly_cap_reached' ? 403 : 429),
            '/rappel/site_CLE': () => reponse({ ok: true }),
        });
        await charger(fetchMock);
        await jusquaLaConversation();
        expect(zone('plafond')?.textContent).toContain('Laissez vos coordonnées');
        const [nom, coord] = Array.from(racine().querySelectorAll('input.mk-saisie')) as HTMLInputElement[];
        // Sans coordonnées : rien ne part.
        (zone('plafondBouton') as HTMLButtonElement).click();
        await attendre();
        expect(appels.find((a) => a.url.includes('/rappel/'))).toBeUndefined();
        nom.value = 'Léa';
        coord.value = '06 55 55 66 66';
        (zone('plafondBouton') as HTMLButtonElement).click();
        await attendre();
        const rappel = appels.find((a) => a.url.includes('/rappel/site_CLE'))!;
        expect(rappel.corps).toEqual({ chemin: '/tarifs', contact: { nom: 'Léa', telephone: '06 55 55 66 66' } });
        expect(zone('merci')?.textContent).toBe('Merci, à bientôt.');
    });
  }

  it('un mail dans le champ part comme un mail', async () => {
        const { appels, fetchMock } = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () => reponse({ detail: { code: 'monthly_cap_reached' } }, 403),
            '/rappel/': () => reponse({ ok: true }),
        });
        await charger(fetchMock);
        await jusquaLaConversation();
        const coord = Array.from(racine().querySelectorAll('input.mk-saisie'))[1] as HTMLInputElement;
        coord.value = 'lea@exemple.fr';
        (zone('plafondBouton') as HTMLButtonElement).click();
        await attendre();
        expect(appels.find((a) => a.url.includes('/rappel/'))!.corps.contact).toEqual({ mail: 'lea@exemple.fr' });
  });
});

describe("l'avis", () => {
    async function versLAvis(extra: Record<string, (a: Appel) => Response> = {}) {
        const s = serveur({
            '/config': () => reponse(CONFIG),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () =>
                reponse({ session_token: 'emb_session_AVIS', workflow_run_id: 3, config: { workflow_id: 9 }, widget_type: 'chat',
                    chat_session: { revision: 1, state: 'running', is_completed: false, turns: [] } }),
            '/end': () => reponse({ revision: 2, state: 'completed', is_completed: true, turns: [] }),
            ...extra,
        });
        await charger(s.fetchMock);
        await jusquaLaConversation();
        (zone('raccrocher') as HTMLButtonElement).click();
        await attendre();
        return s;
    }
    const etoile = (n: number) => racine().querySelector(`[data-zone="etoiles"] button[aria-label="${n} étoile${n > 1 ? 's' : ''}"]`) as HTMLButtonElement;
    const puce = (t: string) => Array.from(racine().querySelectorAll('[data-zone="choix"]')).find((p) => p.textContent === t) as HTMLButtonElement;

    it('une note basse : questions de la déception, rappel avec coordonnées, envoi', async () => {
        const { appels } = await versLAvis({ '/public/embed/avis/': () => reponse({ ok: true }) });
        expect((zone('avisEnvoyer') as HTMLButtonElement).disabled).toBe(true);
        etoile(2).click();
        expect(racine().textContent).toContain('Qu’est-ce qui n’a pas été ?');
        puce('En partie').click();
        puce('Trop lent').click();
        (racine().querySelector('[data-zone="caseRappel"] input') as HTMLInputElement).click();
        expect(zone('casePublication')).toBeNull();
        // Le rappel demandé sans coordonnées ne part pas.
        (zone('avisEnvoyer') as HTMLButtonElement).click();
        await attendre();
        expect(appels.find((a) => a.url.includes('/avis/'))).toBeUndefined();
        const [nom, coord] = Array.from(racine().querySelectorAll('input.mk-saisie')) as HTMLInputElement[];
        nom.value = 'Claire';
        nom.dispatchEvent(new Event('input'));
        coord.value = 'claire@exemple.fr';
        coord.dispatchEvent(new Event('input'));
        (zone('avisEnvoyer') as HTMLButtonElement).click();
        await attendre();
        const envoi = appels.find((a) => a.url.endsWith('/avis/emb_session_AVIS'))!;
        expect(envoi.corps).toEqual({
            etoiles: 2, raisons: ['Trop lent'], rappel_demande: true, publication_acceptee: false,
            obtenu: 'en_partie', contact: { nom: 'Claire', mail: 'claire@exemple.fr' },
        });
        expect(zone('merci')).not.toBeNull();
    });

    it('une bonne note : la publication, jamais envoyée sans la case', async () => {
        const { appels } = await versLAvis({ '/public/embed/avis/': () => reponse({ ok: true }) });
        etoile(5).click();
        expect(racine().textContent).toContain('Qu’avez-vous le plus apprécié ?');
        expect(zone('caseRappel')).toBeNull();
        (zone('avisEnvoyer') as HTMLButtonElement).click();
        await attendre();
        expect(appels.find((a) => a.url.includes('/avis/'))!.corps.publication_acceptee).toBe(false);
    });

    it("réessaie tant que la conversation n'est pas finie, puis abandonne proprement", async () => {
        let essais = 0;
        const { appels } = await versLAvis({
            '/public/embed/avis/': () => {
                essais += 1;
                return essais < 3
                    ? reponse({ detail: { code: 'conversation_not_finished' } }, 409)
                    : reponse({ ok: true });
            },
        });
        etoile(4).click();
        (zone('avisEnvoyer') as HTMLButtonElement).click();
        await attendre(1600);
        await attendre(1600);
        expect(appels.filter((a) => a.url.includes('/avis/'))).toHaveLength(3);
        expect(zone('merci')).not.toBeNull();
    });

    it('un refus du serveur reste dit, sans perdre la saisie', async () => {
        await versLAvis({ '/public/embed/avis/': () => reponse({ detail: 'non' }, 500) });
        etoile(3).click();
        (zone('avisEnvoyer') as HTMLButtonElement).click();
        await attendre();
        expect(racine().querySelector('[role="alert"]')?.textContent).toContain('indisponible');
        expect(zone('etoiles')).not.toBeNull();
    });

    it('« Fermer » passe l’avis sans rien envoyer', async () => {
        const { appels } = await versLAvis({});
        (zone('avisPasser') as HTMLButtonElement).click();
        expect(zone('merci')).not.toBeNull();
        expect(appels.find((a) => a.url.includes('/avis/'))).toBeUndefined();
    });

    it('avis éteint par le client : le merci suit directement', async () => {
        const s = serveur({
            '/config': () => reponse({ ...CONFIG, apparence: { avis: false } }),
            '/evenement': () => reponse({ ok: true }),
            '/public/embed/init': () =>
                reponse({ session_token: 'x', workflow_run_id: 3, config: { workflow_id: 9 }, widget_type: 'chat',
                    chat_session: { revision: 1, state: 'running', is_completed: false, turns: [] } }),
            '/end': () => reponse({ revision: 2, state: 'completed', is_completed: true, turns: [] }),
        });
        await charger(s.fetchMock);
        await jusquaLaConversation();
        (zone('raccrocher') as HTMLButtonElement).click();
        await attendre();
        expect(zone('etoiles')).toBeNull();
        expect(zone('merci')).not.toBeNull();
    });
});

describe("l'aperçu du portail", () => {
    it('monte le même rendu dans un cadre, sans aucune requête, avec les repères data-zone', async () => {
        const { fetchMock } = serveur({});
        vi.stubGlobal('fetch', fetchMock);
        document.body.innerHTML = '<div id="cadre"></div>';
        delete (window as W).MarkWidget;
        window.eval(source);
        const cadre = document.getElementById('cadre')!;
        const apercu = (window as W).MarkWidget.apercu(cadre, { etat: 'information', apparence: { textes: { bouton_demarrer: 'Allons-y' } } });
        const r = (cadre.querySelector('[data-mark-widget="apercu"]') as HTMLElement).shadowRoot!;
        expect(r.querySelector('[data-zone="demarrer"]')?.textContent).toBe('Allons-y');
        for (const attendu of ['fenetre', 'orbe', 'information', 'demarrer']) {
            expect(r.querySelector(`[data-zone="${attendu}"]`), attendu).not.toBeNull();
        }
        apercu.majApercu({ etat: 'avis', etoiles: 2 });
        for (const attendu of ['etoiles', 'caseRappel', 'avisEnvoyer', 'choix']) {
            expect(r.querySelector(`[data-zone="${attendu}"]`), attendu).not.toBeNull();
        }
        apercu.majApercu({ etat: 'plafond' });
        expect(r.querySelector('[data-zone="plafondBouton"]')).not.toBeNull();
        apercu.majApercu({ etat: 'merci' });
        expect(r.querySelector('[data-zone="merci"]')).not.toBeNull();
        apercu.majApercu({ etat: 'conversation', microRefuse: true });
        expect(r.querySelector('[data-zone="microRefuse"]')).not.toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
        apercu.detruire();
    });

    it('sur un cadre étroit (téléphone), la fenêtre prend tout le cadre', async () => {
        document.body.innerHTML = '<div id="cadre"></div>';
        delete (window as W).MarkWidget;
        window.eval(source);
        const cadre = document.getElementById('cadre')!;
        (window as W).MarkWidget.apercu(cadre, { etat: 'information', largeurCadre: 390 });
        const r = (cadre.querySelector('[data-mark-widget]') as HTMLElement).shadowRoot!;
        expect(r.querySelector('.mk-fenetre')?.classList.contains('mk-plein')).toBe(true);
    });
});

describe('V5 : le widget suit la maquette', () => {
    async function avecConfig(apparence: object, extra: object = {}, couleurs: object = {}) {
        const { fetchMock } = serveur({
            '/config': () => reponse({ ...CONFIG, apparence, couleurs, ...extra }),
            '/evenement': () => reponse({ ok: true }),
        });
        await charger(fetchMock);
    }
    function apercuDans(options: object) {
        const cadre = document.createElement('div');
        document.body.appendChild(cadre);
        delete (window as W).MarkWidget;
        window.eval(source);
        const ap = (window as W).MarkWidget.apercu(cadre, options);
        const r = (cadre.querySelector('[data-mark-widget="apercu"]') as HTMLElement).shadowRoot!;
        return { ap, r };
    }

    it('la fenêtre porte un titre réglable et l’emblème, comme la maquette', async () => {
        await avecConfig({ textes: { titre: 'Showroom de Beauvais' } });
        zone('rond')!.click();
        await attendre();
        expect(zone('titre')?.textContent).toBe('Showroom de Beauvais');
        expect(zone('fenetre')?.getAttribute('aria-label')).toBe('Showroom de Beauvais');
        expect(racine().querySelector('.mk-titre [data-zone="orbe"], .mk-titre img')).not.toBeNull();
    });

    it('« toujours » montre l’accroche tout de suite', async () => {
        await avecConfig({ declenchement: 'toujours' });
        expect(zone('accroche')).not.toBeNull();
    });

    it('« jamais » : le rond seul, le survol ne montre rien', async () => {
        await avecConfig({ declenchement: 'jamais' });
        expect(zone('accroche')).toBeNull();
        zone('rond')!.dispatchEvent(new MouseEvent('mouseenter'));
        await attendre();
        expect(zone('accroche')).toBeNull();
        expect(zone('rond')).not.toBeNull();
    });

    it('« survol » montre l’accroche au survol du rond', async () => {
        await avecConfig({ declenchement: 'survol' });
        expect(zone('accroche')).toBeNull();
        zone('rond')!.dispatchEvent(new MouseEvent('mouseenter'));
        await attendre();
        expect(zone('accroche')).not.toBeNull();
    });

    it('« voix seule » : pas de champ de saisie pendant la conversation vocale', async () => {
        const { ap, r } = apercuDans({ etat: 'conversation', modes: 'voix' });
        expect(r.querySelector('[data-zone="saisieVoix"]')).toBeNull();
        ap.majApercu({ modes: 'voix_et_ecrit', etat: 'conversation' });
        expect(r.querySelector('[data-zone="saisieVoix"]')).not.toBeNull();
        ap.detruire();
    });

    it('l’avis : titre, « passer » et les deux cases viennent des textes réglés', async () => {
        const textes = { avis_titre: 'Votre avis compte', avis_passer: 'Plus tard', case_rappel: 'Rappelez-moi', case_publication: 'Affichez mon avis' };
        const { ap, r } = apercuDans({ etat: 'avis', etoiles: 2, apparence: { textes } });
        expect(r.querySelector('[data-zone="avisTitre"]')?.textContent).toBe('Votre avis compte');
        expect(r.querySelector('[data-zone="avisPasser"]')?.textContent).toBe('Plus tard');
        expect(r.querySelector('[data-zone="caseRappel"]')?.textContent).toBe('Rappelez-moi');
        ap.majApercu({ etat: 'avis', etoiles: 5 });
        expect(r.querySelector('[data-zone="casePublication"]')?.textContent).toBe('Affichez mon avis');
        ap.detruire();
    });

    it('chaque couleur de la maquette s’applique à son élément', async () => {
        const couleurs = {
            raccrocher: '#112233', raccrocher_texte: '#445566', bulle_agent: '#aabbcc', bulle_agent_texte: '#010203',
            bulles_ecrit: '#102030', bulles_ecrit_texte: '#fefefe', champ_saisie: '#eeeeee', champ_saisie_texte: '#333333',
        };
        const { ap, r } = apercuDans({ etat: 'conversation', microRefuse: true, couleurs });
        const style = (nom: string) => (r.querySelector(`[data-zone="${nom}"]`) as HTMLElement).style;
        expect(style('raccrocher').backgroundColor).toBe('rgb(17, 34, 51)');
        expect(style('raccrocher').color).toBe('rgb(68, 85, 102)');
        expect(style('bulleAgent').backgroundColor).toBe('rgb(170, 187, 204)');
        expect(style('bulleAgent').color).toBe('rgb(1, 2, 3)');
        expect(style('bulleVisiteur').backgroundColor).toBe('rgb(16, 32, 48)');
        expect(style('bulleVisiteur').color).toBe('rgb(254, 254, 254)');
        expect(style('saisieEcrite').color).toBe('rgb(51, 51, 51)');
        ap.detruire();
    });

    it('l’aperçu écrit montre un exemple d’échange (de quoi cliquer les deux bulles), jamais envoyé', async () => {
        const { fetchMock } = serveur({});
        vi.stubGlobal('fetch', fetchMock);
        const { ap, r } = apercuDans({ etat: 'conversation', microRefuse: true });
        expect(r.querySelector('[data-zone="bulleAgent"]')).not.toBeNull();
        expect(r.querySelector('[data-zone="bulleVisiteur"]')).not.toBeNull();
        expect(r.querySelector('[data-zone="saisieEcrite"]')).not.toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
        ap.detruire();
    });
});
