/**
 * [.mark] R3 mineur 4 : le fichier « Télécharger (JSON) » ne porte aucun secret.
 *
 * La définition tenue par l'éditeur peut contenir la clé qu'une personne vient de taper (`qa_api_key` du nœud d'analyse) avant
 * tout enregistrement : le serveur la masque en lecture, pas le navigateur. L'export retire donc tout champ de secret des
 * données de chaque nœud, comme le fait l'export vers un client (`secrets_retires`).
 */
const CHAMP_SECRET = /(^|_)(api_?key|secret|token|password|mot_de_passe)$/i;

interface NoeudBrut {
    data?: Record<string, unknown>;
    [cle: string]: unknown;
}

/** Une copie de la définition (`rfInstance.toObject()`) sans aucun champ de secret dans les données des nœuds. */
export function definitionSansSecrets<T extends { nodes?: NoeudBrut[] }>(definition: T): T {
    const copie = structuredClone(definition);
    for (const noeud of copie.nodes ?? []) {
        if (!noeud.data) continue;
        for (const cle of Object.keys(noeud.data)) {
            if (CHAMP_SECRET.test(cle)) delete noeud.data[cle];
        }
    }
    return copie;
}
