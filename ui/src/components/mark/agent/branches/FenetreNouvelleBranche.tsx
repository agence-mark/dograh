"use client";

import { creerUneBrancheApiV1BuilderBranchesWorkflowIdPost } from "@/client/sdk.gen";
import type { BranchesVue } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";

/**
 * [.mark] Partie 3, SA-L3b (maquette `FenetreNouvelleBranche`) : la fenêtre centrée de création. Une copie de travail parallèle,
 * sans aucune part du trafic tant qu'on ne lui en donne pas. La faute de saisie (nom vide, déjà pris) est dite sous le champ.
 */
export const NOM_MAX = 60;

export function fauteDeNom(nom: string, branches: { nom: string }[], t: ReturnType<typeof useLangue>["t"]): string | null {
    const propre = nom.trim().replace(/\s+/g, " ");
    if (!propre) return t({ en: "Give the branch a name.", fr: "Donnez un nom à la branche." });
    if (propre.length > NOM_MAX) return t({ en: "60 characters at most.", fr: "60 caractères au plus." });
    if (branches.some((b) => b.nom.trim().toLowerCase() === propre.toLowerCase())) {
        return t({ en: "A branch already has this name.", fr: "Une branche porte déjà ce nom." });
    }
    return null;
}

export function FenetreNouvelleBranche({
    agentId,
    ouverte,
    fermer,
    vue,
    cree,
}: {
    agentId: number;
    ouverte: boolean;
    fermer: () => void;
    vue: BranchesVue | null;
    /** Appelée avec l'identifiant de la branche créée (l'écran l'ouvre). */
    cree: (brancheId: number) => void;
}) {
    const { t } = useLangue();
    const principale = vue?.branches.find((b) => b.principale);
    const enLigne = t({ en: "Live version", fr: "Version en ligne" });
    const versions = (principale?.versions ?? []).filter((v) => v.numero !== null);
    const options = [enLigne, ...versions.map((v) => `v${v.numero}`)];
    return (
        <FenetreChamps
            ouverte={ouverte}
            fermer={fermer}
            titre={t({ en: "New branch", fr: "Nouvelle branche" })}
            info={t({
                en: "A parallel working copy: you edit and test it without touching the calls in progress. It receives no call until you give it a share of the traffic.",
                fr: "Une copie de travail parallèle : vous la modifiez et la testez sans toucher aux appels en cours. Elle ne reçoit aucun appel tant que vous ne lui donnez pas de part du trafic.",
            })}
            valider={t({ en: "Create the branch", fr: "Créer la branche" })}
            sections={[
                {
                    champs: [
                        { id: "depuis", t: "choix", l: t({ en: "From which version", fr: "Depuis quelle version" }), o: options, v: enLigne },
                        { id: "nom", t: "texte", l: t({ en: "Name", fr: "Nom" }), v: "" },
                    ],
                },
            ]}
            verifier={(valeurs) => {
                const faute = fauteDeNom(String(valeurs.nom ?? ""), vue?.branches ?? [], t);
                return faute ? { nom: faute } : null;
            }}
            onValider={async (valeurs) => {
                const choix = String(valeurs.depuis ?? "");
                const depuis = /^v(\d+)$/.exec(choix);
                const nom = String(valeurs.nom ?? "").trim().replace(/\s+/g, " ");
                const r = await creerUneBrancheApiV1BuilderBranchesWorkflowIdPost({
                    path: { workflow_id: agentId },
                    body: { nom, depuis_version: depuis ? Number(depuis[1]) : null },
                });
                if (r.error || !r.data) {
                    notifier.echec({ fr: "Création impossible. Réessayez.", en: "Could not create the branch. Try again." }, { erreur: r.error });
                    return false;
                }
                notifier.succes({ fr: `Branche « ${nom} » créée, sans trafic.`, en: `Branch "${nom}" created, with no traffic.` });
                cree((r.data as { id: number }).id);
                return true;
            }}
        />
    );
}
