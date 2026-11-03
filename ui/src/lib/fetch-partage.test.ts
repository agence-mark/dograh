/** [.mark] L : deux lectures identiques en vol partagent une requête ; rien d'autre n'est partagé. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPartage, viderLesLecturesEnVol } from "./fetch-partage";

const appels: Request[] = [];
let liberer: (() => void)[] = [];

beforeEach(() => {
    appels.length = 0;
    liberer = [];
    viderLesLecturesEnVol();
    vi.stubGlobal(
        "fetch",
        vi.fn((r: Request) => {
            appels.push(r);
            return new Promise<Response>((ok) => liberer.push(() => ok(new Response(JSON.stringify({ n: appels.length }), { status: 200 }))));
        }),
    );
});
afterEach(() => vi.unstubAllGlobals());

const get = (url: string, init: RequestInit = {}) => new Request(`http://api.test${url}`, { headers: { Authorization: "Bearer a" }, ...init });

describe("fetchPartage", () => {
    it("deux lectures identiques en vol : une seule requête, une réponse lisible par chacune", async () => {
        const a = fetchPartage(get("/api/v1/workflow/1/versions"));
        const b = fetchPartage(get("/api/v1/workflow/1/versions"));
        liberer.forEach((f) => f());
        const [ra, rb] = await Promise.all([a, b]);
        expect(appels).toHaveLength(1);
        expect(await ra.json()).toEqual({ n: 1 });
        expect(await rb.json()).toEqual({ n: 1 });
    });

    it("une lecture après l'arrivée de la première repart au serveur (rien de périmé)", async () => {
        const a = fetchPartage(get("/api/v1/x"));
        liberer.forEach((f) => f());
        await a;
        const b = fetchPartage(get("/api/v1/x"));
        liberer.forEach((f) => f());
        await b;
        expect(appels).toHaveLength(2);
    });

    it("adresse, session ou organisation différentes : requêtes séparées", () => {
        void fetchPartage(get("/api/v1/x"));
        void fetchPartage(get("/api/v1/y"));
        void fetchPartage(get("/api/v1/x", { headers: { Authorization: "Bearer b" } }));
        void fetchPartage(get("/api/v1/x", { headers: { Authorization: "Bearer a", "X-Mark-Organisation": "2" } }));
        expect(appels).toHaveLength(4);
    });

    it("une écriture et un flux ne sont jamais partagés", () => {
        void fetchPartage(get("/api/v1/x", { method: "POST", body: "{}" }));
        void fetchPartage(get("/api/v1/x", { method: "POST", body: "{}" }));
        void fetchPartage(get("/api/v1/builder/live"));
        void fetchPartage(get("/api/v1/builder/live"));
        void fetchPartage(get("/api/v1/z", { headers: { Accept: "text/event-stream" } }));
        void fetchPartage(get("/api/v1/z", { headers: { Accept: "text/event-stream" } }));
        expect(appels).toHaveLength(6);
    });

    it("l'annulation d'un appelant ne coupe pas la lecture des autres", async () => {
        const stop = new AbortController();
        const a = fetchPartage(get("/api/v1/x", { signal: stop.signal }));
        const b = fetchPartage(get("/api/v1/x"));
        stop.abort();
        await expect(a).rejects.toMatchObject({ name: "AbortError" });
        liberer.forEach((f) => f());
        expect((await b).status).toBe(200);
        expect(appels).toHaveLength(1);
    });
});
