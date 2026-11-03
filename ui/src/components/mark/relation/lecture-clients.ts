import { listerClientsApiV1RelationClientsGet } from "@/client/sdk.gen";

/**
 * Une seule lecture de la liste des clients par page (bonnes pratiques de l'écran) : la barre latérale (compteur de
 * Messages) et la page lisent la même donnée ; les appels rapprochés partagent la même requête. Passé le délai, une
 * relecture (« Réessayer », rechargement) repart au serveur.
 */
const DELAI_MS = 2000;
let derniere: { promesse: ReturnType<typeof listerClientsApiV1RelationClientsGet>; a: number } | null = null;

export function lireClientsRelation() {
    const maintenant = Date.now();
    if (!derniere || maintenant - derniere.a > DELAI_MS) {
        derniere = { promesse: listerClientsApiV1RelationClientsGet(), a: maintenant };
    }
    return derniere.promesse;
}

/** Pour les tests : oublie la lecture en cours. */
export const oublierLectureClients = () => {
    derniere = null;
};
