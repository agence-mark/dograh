// @vitest-environment node
/**
 * [.mark] Partie 3, sous-lot 19 : l'inventaire des fenêtres centrées. Toute fenêtre s'ouvre dans le panneau de droite, SAUF
 * celles de cette liste (`07-fenetres-panneau-ou-centrees.md`, règle d'Evan du 04/11). Une fenêtre qui se déclare `centree`
 * sans figurer ici fait échouer le test : on l'ajoute ici AVEC sa raison, ou on la laisse au panneau.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..", "..");
const joli = (f: string) => relative(SRC, f).split(sep).join("/");
function parcourir(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (nom === "client" || nom === "node_modules") return [];
        return statSync(chemin).isDirectory() ? parcourir(chemin) : [chemin];
    });
}

/** Les fenêtres qui restent au milieu de l'écran, et pourquoi. */
export const CENTREES: Record<string, string> = {
    "components/mark/site/EditeurWidget.tsx": "configurateur du widget du site",
    "components/mark/integrations/OngletLogiciels.tsx": "catalogue des logiciels ; Brancher / proposer un logiciel",
    "components/mark/modeles/FenetreService.tsx": "configurateur de modèle (fournisseur, service)",
    "components/mark/reglages/CerveauxReglages.tsx": "choix du modèle et de la clé (comme le configurateur de modèle)",
    "components/VoiceSelectorModal.tsx": "choix d'une voix chez un fournisseur",
    "components/mark/agent/FenetreCreationAgent.tsx": "création : Nouvel agent",
    "app/campaigns/new/page.tsx": "création : Nouvelle campagne (la page est la fenêtre)",
    "components/mark/installation/FenetreNouveauClient.tsx": "création : Nouveau client",
    "components/mark/relation/EcransRelation.tsx": "création : Nouveau client ; confirmation de suppression",
    "components/mark/agent/publication/FenetreDePublication.tsx": "confirmation de publication (Prêt à publier, Forcer)",
    "components/mark/groupe/PublierLeGroupe.tsx": "confirmation de publication du groupe",
    "components/mark/groupe/ChoixSpecialisesArchivage.tsx": "confirmation d'archivage",
    "components/mark/groupe/DialogueNom.tsx": "saisie courte : un nom",
    "components/mark/outils/versions/BoutonPasser.tsx": "petite confirmation : Passer à la v5",
    "components/mark/parametres-organisation/BoutonAppliquerATous.tsx": "geste qui touche tous les établissements",
    "components/mark/reglages-agent/RecetteDeLAgent.tsx": "avertissement avant un test sur l'agent publié",
    "components/mark/studio/suppression-confirmee.tsx": "confirmation de suppression",
    "components/builder/chat/ListeDesFils.tsx": "confirmation de suppression d'un chat",
    "components/builder/chat/FenetreRestauration.tsx": "petite confirmation : revenir à une version",
    "components/builder/chat/plafond-du-mois.tsx": "plafond de dépense atteint : interrompt le geste",
    "components/builder/chat/permissions-du-chat.tsx": "« Tout permettre » dans ce chat : confirmation d'un geste qui élargit les droits du builder (09 de la revue)",
    "components/mark/graphe/BriqueAgent.tsx": "choix court d'un agent",
    "components/layout/SidebarOrganizationSwitcher.tsx": "choix court d'une organisation",
    "components/mark/studio/fenetre-profil.tsx": "Mon profil : saisie courte, ouverte depuis la barre latérale",
    "app/campaigns/[campaignId]/page.tsx": "confirmation ; relance de vrais appels",
    "app/files/page.tsx": "dépôt d'un fichier : saisie courte",
    "app/workflow/[workflowId]/run/[runId]/components/ApiKeyErrorDialog.tsx": "erreur bloquante qui interrompt",
    "app/workflow/[workflowId]/run/[runId]/components/WorkflowConfigErrorDialog.tsx": "erreur bloquante qui interrompt",
    "components/workflow/UploadWorkflowButton.tsx": "dépôt d'un fichier : saisie courte",
    "components/workflow/folders/FolderFormDialog.tsx": "saisie courte : un nom de dossier",
};

/** Les enveloppes qui portent la propriété `centree` (elles la définissent, elles ne décident rien). */
const ENVELOPPES = new Set([
    "components/ui/dialog.tsx",
    "components/mark/studio/fenetre-champs.tsx",
    "components/mark/studio/fenetre-large.tsx",
    "components/mark/studio/fenetre-libre.tsx",
    "components/mark/studio/fenetre-onglets.tsx",
    "components/mark/studio/panneau-droit.tsx",
]);
/** Elles demandent explicitement le panneau (`centree={false}`) alors que la règle des deux champs les centrerait. Sous-lot 21 :
 * la fenêtre de la transition (`FenetreTransition`) n'a plus besoin de le demander (elle n'est pas une fenêtre à champs). */
const AU_PANNEAU_EXPLICITE = new Set<string>();

const declarent = () =>
    parcourir(SRC)
        .map(joli)
        .filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f))
        .filter((f) => /<(Dialog|Fenetre\w*)\s+centree\b/.test(readFileSync(join(SRC, f), "utf8")))
        .filter((f) => !ENVELOPPES.has(f) && !AU_PANNEAU_EXPLICITE.has(f));

describe("l'inventaire des fenêtres centrées (sous-lot 19)", () => {
    it("toute fenêtre qui se déclare centrée figure dans la liste, avec sa raison", () => {
        const inconnues = declarent().filter((f) => !(f in CENTREES));
        expect(inconnues).toEqual([]);
    });

    it("toute fenêtre de la liste est encore centrée (la liste ne ment pas)", () => {
        const presentes = new Set(declarent());
        expect(Object.keys(CENTREES).filter((f) => !presentes.has(f))).toEqual([]);
    });

    it("chaque entrée a une raison écrite", () => {
        expect(Object.entries(CENTREES).filter(([, raison]) => raison.trim().length < 5)).toEqual([]);
    });

    it("les fenêtres de modification d'un objet (étape, transition, tests, qualité, versions) ne sont pas centrées", () => {
        const sansCentree = [
            "components/flow/nodes/common/NodeEditDialog.tsx",
            "components/mark/graphe/FenetreTransition.tsx",
            "components/mark/agent/branches/FenetreVersions.tsx",
            "components/mark/agent/branches/FenetreRepartition.tsx",
            "components/mark/agent/branches/FenetreFusion.tsx",
            "components/mark/qualite/AlertesDesAppels.tsx",
            "components/builder/tests/FenetreAttaques.tsx",
        ];
        for (const f of sansCentree) expect(readFileSync(join(SRC, f), "utf8"), f).not.toMatch(/<(Dialog|Fenetre\w*)\s+centree\b/);
    });
});
