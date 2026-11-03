/**
 * [.mark] La table unique des redirections (U1, sous-lot 4) : chaque ancienne adresse de l'écran, vers sa place dans
 * la refonte (`/labo/*`, `/clients/<org>/*`, `/agents/<id>`, `/conversations/<id>`).
 *
 * Lue par `next.config.ts` (les redirections réelles) et par les tests (l'inventaire des anciennes adresses). Les
 * redirections ne sont pas permanentes : un navigateur ne garde pas l'ancienne réponse si la table change.
 * Les anciennes adresses sans organisation (`/workflow`, `/tools`...) mènent à l'espace Labo ; l'organisation d'un
 * client est lue dans son adresse (U2).
 */
export type Redirection = { source: string; destination: string };

export const REDIRECTIONS: Redirection[] = [
    // Retirés (amont inutile) : leur place est l'accueil du Labo, qui est le builder.
    { source: "/overview", destination: "/labo" },
    { source: "/automation", destination: "/labo" },
    { source: "/billing", destination: "/labo" },
    // La création d'un agent par l'amont est remplacée par le builder (le constat C13 de l'accueil d'un compte neuf est à U2).
    { source: "/workflow/create", destination: "/labo" },

    // La connexion a sa place dans le nouveau design (U2 ter) ; l'inscription libre n'existe plus que pour le premier compte.
    { source: "/auth/login", destination: "/connexion" },

    // Agents, éditeur et conversations.
    { source: "/workflow", destination: "/labo/agents" },
    { source: "/workflow/:workflowId", destination: "/agents/:workflowId" },
    { source: "/workflow/:workflowId/runs", destination: "/agents/:workflowId/runs" },
    { source: "/workflow/:workflowId/settings", destination: "/agents/:workflowId/settings" },
    { source: "/workflow/:workflowId/tests", destination: "/agents/:workflowId/tests" },
    { source: "/workflow/:workflowId/run/:runId", destination: "/conversations/:runId?agent=:workflowId" },

    // Les rubriques du menu.
    { source: "/campaigns", destination: "/labo/campagnes" },
    { source: "/campaigns/new", destination: "/labo/campagnes/new" },
    { source: "/campaigns/:campaignId", destination: "/labo/campagnes/:campaignId" },
    { source: "/campaigns/:campaignId/edit", destination: "/labo/campagnes/:campaignId/edit" },
    { source: "/model-configurations", destination: "/labo/modeles" },
    { source: "/cles", destination: "/labo/cles" },
    { source: "/telephony-configurations", destination: "/labo/telephonie" },
    { source: "/telephony-configurations/:configId", destination: "/labo/telephonie/:configId" },
    { source: "/tools", destination: "/labo/outils" },
    { source: "/tools/:toolUuid", destination: "/labo/outils/:toolUuid" },
    { source: "/files", destination: "/labo/connaissances" },
    // Les enregistrements et le cache de la voix sont dans Entreprise › Écoute et sons (E56).
    { source: "/recordings", destination: "/labo/entreprise?onglet=ecoute" },
    { source: "/labo/sons", destination: "/labo/entreprise?onglet=ecoute" },
    { source: "/clients/:org/sons", destination: "/clients/:org/entreprise?onglet=ecoute" },
    { source: "/api-keys", destination: "/labo/reglages?onglet=organisation&section=developpeurs" },
    { source: "/usage", destination: "/labo/conversations" },
    { source: "/reports", destination: "/labo/qualite" },
    { source: "/bibliotheque", destination: "/labo/bibliotheque" },
    { source: "/a-trier", destination: "/labo/a-ameliorer" },
    { source: "/alertes", destination: "/labo/alertes" },
    { source: "/settings", destination: "/labo/reglages" },
];

// Une source ne contient que des segments littéraux (lettres et tirets) et des `:nom` ; un `:nom` vaut un segment.
const versRegex = (source: string) => new RegExp("^" + source.replace(/:[A-Za-z]+/g, "([^/]+)") + "/?$");

/**
 * Où mène une adresse (le même appariement que Next : premier motif qui convient, un `:nom` = un segment).
 * Renvoie `null` si l'adresse n'est pas redirigée.
 */
export function destinationDe(adresse: string): string | null {
    for (const { source, destination } of REDIRECTIONS) {
        const m = versRegex(source).exec(adresse);
        if (!m) continue;
        const noms = [...source.matchAll(/:([A-Za-z]+)/g)].map((x) => x[1]);
        return noms.reduce((d, nom, i) => d.split(`:${nom}`).join(m[i + 1]), destination);
    }
    return null;
}
