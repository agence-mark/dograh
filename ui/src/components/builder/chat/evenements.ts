/**
 * [.mark] builder partie 2, U5 : le fil du chat vu de l'écran. Les événements de la table (rejoués à l'ouverture, puis suivis en
 * direct) deviennent les lignes du fil. Pur : le même flux donne toujours les mêmes lignes, que l'écran ait été rechargé ou non.
 */

export type EvenementDuFil = { type: string; [cle: string]: unknown };

export type CarteDuFil = { type: string; [cle: string]: unknown };

export type LigneDuFil =
    | { genre: "message"; id: number; texte: string }
    | { genre: "texte"; texte: string }
    | { genre: "action"; id: string; nom: string; arguments: Record<string, unknown>; fini: boolean; ok?: boolean; resultat?: unknown }
    | { genre: "carte"; carte: CarteDuFil }
    | { genre: "erreur"; message: string }
    | { genre: "fin"; raison: string }
    | { genre: "reprise" };

export type EtapeDuPlan = { libelle: string; etat: "fait" | "en_cours" | "a_venir" };

/** Applique un événement (identifiant `id` dans la table) aux lignes du fil. */
export function appliquer(lignes: LigneDuFil[], id: number, e: EvenementDuFil): LigneDuFil[] {
    switch (e.type) {
        case "message":
            return [...lignes, { genre: "message", id, texte: String(e.texte ?? "") }];
        case "reprise":
            return [...lignes, { genre: "reprise" }];
        case "texte": {
            const dernier = lignes[lignes.length - 1];
            const morceau = String(e.texte ?? "");
            if (dernier?.genre === "texte") return [...lignes.slice(0, -1), { genre: "texte", texte: dernier.texte + morceau }];
            return [...lignes, { genre: "texte", texte: morceau }];
        }
        case "action":
            return [
                ...lignes,
                { genre: "action", id: String(e.id), nom: String(e.nom), arguments: (e.arguments as Record<string, unknown>) ?? {}, fini: false },
            ];
        case "resultat":
            return lignes.map((l) =>
                l.genre === "action" && l.id === String(e.id) ? { ...l, fini: true, ok: Boolean(e.ok), resultat: e.resultat } : l,
            );
        case "carte": {
            const carte = e.carte as CarteDuFil;
            // Le plan est UNE carte tenue à jour : la nouvelle remplace l'ancienne à sa place.
            if (carte.type === "plan" && lignes.some((l) => l.genre === "carte" && l.carte.type === "plan")) {
                return lignes.map((l) => (l.genre === "carte" && l.carte.type === "plan" ? { genre: "carte", carte } : l));
            }
            return [...lignes, { genre: "carte", carte }];
        }
        case "depense_reponse":
            // La personne a répondu à l'annonce d'une dépense : la carte garde sa place et change d'état.
            return lignes.map((l) =>
                l.genre === "carte" && l.carte.type === "depense" && l.carte.id === e.id ? { genre: "carte", carte: { ...l.carte, statut: e.statut } } : l,
            );
        case "autorisation_reponse":
            // N1 : la personne a répondu à une carte d'autorisation (ou retiré « pour ce chat ») : la carte garde sa place et change d'état.
            return lignes.map((l) =>
                l.genre === "carte" && l.carte.type === "autorisation" && l.carte.id === e.id ? { genre: "carte", carte: { ...l.carte, statut: e.statut } } : l,
            );
        case "delegation":
            return [...lignes, { genre: "carte", carte: { type: "delegation", id: e.id, usage: e.usage, total: e.total, modele: e.modele, fini: false } }];
        case "delegation_fin":
            return lignes.map((l) =>
                l.genre === "carte" && l.carte.type === "delegation" && l.carte.id === e.id ? { genre: "carte", carte: { ...l.carte, fini: true, cout: e.cout } } : l,
            );
        case "erreur":
            // R3 M5 : le texte du serveur n'entre pas dans le fil (il part dans « Détails » d'une notification, voir `useFil`).
            return [...lignes, { genre: "erreur", message: "" }];
        case "fin":
            // N1 : « attente » = une carte d'autorisation attend la personne ; la carte le dit, pas de ligne de fin.
            return e.raison === "fin" || e.raison === "tours" || e.raison === "attente" ? lignes : [...lignes, { genre: "fin", raison: String(e.raison ?? "") }];
        case "retrait": {
            // « Modifier et relancer » : le message retiré et tout ce qui a suivi disparaissent du fil.
            const rang = lignes.findIndex((l) => l.genre === "message" && l.id === Number(e.depuis));
            return rang === -1 ? lignes : lignes.slice(0, rang);
        }
        default:
            return lignes;
    }
}

export function planCourant(lignes: LigneDuFil[]): EtapeDuPlan[] | null {
    for (let i = lignes.length - 1; i >= 0; i--) {
        const l = lignes[i];
        if (l.genre === "carte" && l.carte.type === "plan") return l.carte.etapes as EtapeDuPlan[];
    }
    return null;
}

/** Le dernier message de la personne : celui qu'on peut modifier et relancer. */
export function dernierMessage(lignes: LigneDuFil[]): { id: number; texte: string } | null {
    for (let i = lignes.length - 1; i >= 0; i--) {
        const l = lignes[i];
        if (l.genre === "message") return { id: l.id, texte: l.texte };
    }
    return null;
}

/** Découpe un flux SSE en `{ id, evenement }` (un bloc peut arriver en deux morceaux). */
export async function* lireLesBlocs(flux: ReadableStream<Uint8Array>): AsyncGenerator<{ id: number; evenement: EvenementDuFil }> {
    const lecteur = flux.getReader();
    const decodeur = new TextDecoder();
    let reste = "";
    const lire = (bloc: string) => {
        const lignes = bloc.split("\n");
        const ligneId = lignes.find((l) => l.startsWith("id: "));
        const ligneData = lignes.find((l) => l.startsWith("data: "));
        if (!ligneId || !ligneData) return null;
        try {
            const evenement = JSON.parse(ligneData.slice(6)) as EvenementDuFil;
            return evenement && typeof evenement.type === "string" ? { id: Number(ligneId.slice(4)), evenement } : null;
        } catch {
            return null;
        }
    };
    try {
        for (;;) {
            const { done, value } = await lecteur.read();
            if (done) break;
            reste += decodeur.decode(value, { stream: true });
            let coupure = reste.indexOf("\n\n");
            while (coupure !== -1) {
                const bloc = lire(reste.slice(0, coupure));
                reste = reste.slice(coupure + 2);
                if (bloc) yield bloc;
                coupure = reste.indexOf("\n\n");
            }
        }
    } finally {
        lecteur.releaseLock();
    }
}
