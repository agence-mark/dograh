/**
 * [.mark] L (fluidité) : « une seule lecture par donnée et par page ». Une page monte plusieurs composants qui lisent
 * la même chose (la fiche de l'agent, ses versions, les réglages de l'organisation...) : chacun envoyait sa requête.
 * Ici, deux lectures identiques (GET, même adresse, même session, même organisation) lancées pendant que la première
 * est encore en vol partagent UNE requête ; chaque appelant reçoit sa propre copie de la réponse. Rien n'est gardé
 * une fois la réponse arrivée : la lecture suivante repart au serveur (jamais de donnée périmée).
 * Jamais partagés : les écritures et les flux (SSE, `/live`). Chaque appelant reste annulable seul : l'annulation de
 * l'un ne coupe pas la lecture des autres.
 */
import { ENTETE_ORGANISATION } from "@/lib/espaceCourant";

const enVol = new Map<string, Promise<Response>>();

const estUnFlux = (requete: Request) =>
    (requete.headers.get("Accept") ?? "").includes("text/event-stream") || /\/(live|flux|stream|events)(\/|\?|$)/.test(new URL(requete.url).pathname);

const annulee = () => new DOMException("The operation was aborted.", "AbortError");

export function fetchPartage(entree: Request | string | URL, init?: RequestInit): Promise<Response> {
    const requete = entree instanceof Request && !init ? entree : new Request(entree, init);
    if (requete.method !== "GET" || estUnFlux(requete)) return fetch(requete);
    const cle = [requete.url, requete.headers.get("Authorization"), requete.headers.get(ENTETE_ORGANISATION), requete.headers.get("Accept")].join("|");
    let partagee = enVol.get(cle);
    if (!partagee) {
        // La requête partagée n'écoute pas le signal du premier appelant : sinon son annulation coupe celle des autres.
        const sansSignal = new Request(requete, { signal: new AbortController().signal });
        partagee = fetch(sansSignal);
        enVol.set(cle, partagee);
        const oublier = () => {
            if (enVol.get(cle) === partagee) enVol.delete(cle);
        };
        partagee.then(oublier, oublier);
    }
    const reponse = partagee.then((r) => r.clone());
    if (requete.signal.aborted) return Promise.reject(annulee());
    return new Promise<Response>((resoudre, rejeter) => {
        const surAnnulation = () => rejeter(annulee());
        requete.signal.addEventListener("abort", surAnnulation, { once: true });
        reponse.then(
            (r) => {
                requete.signal.removeEventListener("abort", surAnnulation);
                resoudre(r);
            },
            (e) => {
                requete.signal.removeEventListener("abort", surAnnulation);
                rejeter(e);
            },
        );
    });
}

/** Pour les tests : vide les lectures en vol. */
export const viderLesLecturesEnVol = () => enVol.clear();
