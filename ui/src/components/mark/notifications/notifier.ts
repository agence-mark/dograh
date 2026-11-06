/**
 * [.mark] `notifier` : le SEUL moyen d'afficher une notification passagère (`15-notifications.md`).
 *
 * Aucun fichier de l'écran n'appelle `sonner` ni `toast(` : un test le vérifie (`aucun-appel-direct.test.ts`).
 *
 *   notifier.succes({ fr: "Agent dupliqué.", en: "Agent duplicated." });
 *   notifier.echec({ fr: "Duplication impossible. Réessayez.", en: "Could not duplicate. Try again." }, { erreur, reessayer });
 *
 * Règles : une phrase, deux au plus ; jamais le texte brut d'une erreur serveur (il passe par `erreur`, montré à
 * l'équipe seulement dans « Détails ») ; un bouton facultatif (Annuler, Publier, Réessayer, Ouvrir).
 */
import { publishWorkflowApiV1WorkflowWorkflowIdPublishPost } from "@/client/sdk.gen";
import type { Texte } from "@/components/mark/langue/langue";
import { detailFromError } from "@/lib/apiError";

import { ajouter, type BoutonNotif, DELAI_ANNULER_MS, fermer, remplacer, type SorteNotif } from "./magasin";

export interface OptionsNotif {
    /** L'erreur d'origine (réponse du client d'API, `Error`, texte) : montrée à l'équipe seulement, dans « Détails ». */
    erreur?: unknown;
    /** Bouton « Réessayer » : relance l'action. */
    reessayer?: () => void;
    /** Bouton libre (« Ouvrir », « Ouvrir la copie »…). */
    bouton?: BoutonNotif;
    /**
     * « Publier » : bouton qui publie l'agent affiché (remplace la phrase de rappel). `true` = l'agent déclaré par
     * l'écran (`declarerAgentCourant`) ; un nombre = cet agent. Sans agent connu, la phrase de rappel est gardée.
     */
    publier?: boolean | number;
    /** Deux appels de même groupe ne s'empilent pas : le second remplace le premier. */
    groupe?: string;
}

const REESSAYER: Texte = { fr: "Réessayer", en: "Retry" };
const PUBLIER: Texte = { fr: "Publier", en: "Publish" };
const ANNULER: Texte = { fr: "Annuler", en: "Undo" };

/** Le motif technique d'une erreur, en une chaîne (vide si rien d'utile). */
export function motifDe(erreur: unknown): string {
    if (erreur === undefined || erreur === null) return "";
    if (erreur instanceof Error) return erreur.message;
    return detailFromError(erreur, "");
}

// L'agent dont l'écran est ouvert : posé par les pages de réglages (voir `useAgentCourant`), lu par « Publier ».
let agentCourant: number | null = null;
/** Pose l'agent courant ; rend la fonction qui le retire (seulement s'il est encore celui-là). */
export const declarerAgentCourant = (id: number | null): (() => void) => {
    agentCourant = id;
    return () => {
        if (agentCourant === id) agentCourant = null;
    };
};

const RAPPEL: Texte = { fr: " Publiez l'agent pour appliquer.", en: " Publish the agent to apply." };

function boutonDe(o: OptionsNotif): BoutonNotif | undefined {
    if (o.bouton) return o.bouton;
    if (o.reessayer) return { libelle: REESSAYER, action: o.reessayer };
    const id = typeof o.publier === "number" ? o.publier : o.publier ? agentCourant : null;
    if (id !== null && id !== undefined) return { libelle: PUBLIER, action: () => void publierAgent(id) };
    return undefined;
}

/** SA-L3c : la principale protégée refuse toute écriture ; quelle que soit l'action, la phrase dit pourquoi et quoi faire. */
const PRINCIPALE_PROTEGEE: Texte = {
    fr: "La branche principale est protégée. Travaillez sur une branche, puis fusionnez-la après relecture.",
    en: "The main branch is protected. Work on a branch, then merge it after a review.",
};
const estProtegee = (erreur: unknown) => (erreur as { code?: unknown } | null | undefined)?.code === "principale_protegee";

function afficher(sorte: SorteNotif, texte: Texte, o: OptionsNotif = {}, cle?: number): number {
    const detail = motifDe(o.erreur);
    if (sorte === "echec" && estProtegee(o.erreur)) texte = PRINCIPALE_PROTEGEE;
    const bouton = boutonDe(o);
    // « Publier » demandé mais aucun agent connu : la phrase de rappel reprend le rôle du bouton.
    const sansBouton = o.publier && !bouton ? { fr: texte.fr + RAPPEL.fr, en: texte.en + RAPPEL.en } : texte;
    const entree = { sorte, texte: sansBouton, bouton, detail: detail || undefined, groupe: o.groupe };
    return cle === undefined ? ajouter(entree) : remplacer(cle, entree);
}

/** Une notification « en cours » qui devient succès ou échec dans la même fenêtre. */
export interface EnCours {
    cle: number;
    succes: (texte: Texte, o?: OptionsNotif) => void;
    echec: (texte: Texte, o?: OptionsNotif) => void;
    fermer: () => void;
}

// Suppressions différées : exécutées au bout de 5 s, ou tout de suite si la page se ferme.
const enAttente = new Set<() => void>();
if (typeof window !== "undefined") {
    window.addEventListener("pagehide", () => [...enAttente].forEach((f) => f()));
}

export const notifier = {
    succes: (texte: Texte, o?: OptionsNotif) => afficher("succes", texte, o),
    echec: (texte: Texte, o?: OptionsNotif) => afficher("echec", texte, o),
    avertissement: (texte: Texte, o?: OptionsNotif) => afficher("avertissement", texte, o),
    information: (texte: Texte, o?: OptionsNotif) => afficher("information", texte, o),
    enCours(texte: Texte, o?: OptionsNotif): EnCours {
        const cle = afficher("encours", texte, o);
        return {
            cle,
            succes: (t, opt) => void afficher("succes", t, opt, cle),
            echec: (t, opt) => void afficher("echec", t, opt, cle),
            fermer: () => fermer(cle),
        };
    },
    /**
     * Suit une action asynchrone : « en cours », puis succès ou échec dans la même fenêtre. `echecSi` traite comme un
     * échec une réponse reçue mais refusée (le client d'API ne lève pas d'exception sur une erreur HTTP).
     */
    suivre<T>(
        promesse: Promise<T>,
        m: { encours: Texte; succes: Texte; echec: Texte; echecSi?: (valeur: T) => unknown; reessayer?: () => void; groupe?: string },
    ): void {
        const cours = notifier.enCours(m.encours, { groupe: m.groupe });
        promesse.then(
            (valeur) => {
                const refus = m.echecSi?.(valeur);
                if (refus) cours.echec(m.echec, { erreur: refus, reessayer: m.reessayer, groupe: m.groupe });
                else cours.succes(m.succes, { groupe: m.groupe });
            },
            (erreur) => cours.echec(m.echec, { erreur, reessayer: m.reessayer, groupe: m.groupe }),
        );
    },
    /** Action déjà faite et réversible (déplacer, archiver) : « Annuler » appelle `inverse`. */
    reversible(texte: Texte, inverse: () => void | Promise<unknown>, o?: OptionsNotif): number {
        return ajouter({
            sorte: "succes",
            texte,
            groupe: o?.groupe,
            bouton: {
                libelle: ANNULER,
                action: () => {
                    void inverse();
                    afficher("information", { fr: "Action annulée.", en: "Action undone." }, { groupe: "annulee" });
                },
            },
        });
    },
    /**
     * Suppression différée : `executer` ne part qu'au bout de 5 s ; « Annuler » l'empêche et appelle `restaurer`
     * (remettre l'élément à l'écran). Fermer la notification avant ne l'annule pas.
     */
    annulable(texte: Texte, a: { executer: () => void | Promise<unknown>; restaurer?: () => void }): number {
        let fait = false;
        const lancer = () => {
            if (fait) return;
            fait = true;
            clearTimeout(id);
            enAttente.delete(lancer);
            void a.executer();
        };
        const id = setTimeout(lancer, DELAI_ANNULER_MS);
        enAttente.add(lancer);
        return ajouter({
            sorte: "succes",
            texte,
            duree: DELAI_ANNULER_MS,
            bouton: {
                libelle: ANNULER,
                action: () => {
                    if (fait) return;
                    fait = true;
                    clearTimeout(id);
                    enAttente.delete(lancer);
                    a.restaurer?.();
                    afficher("information", { fr: "Action annulée.", en: "Action undone." }, { groupe: "annulee" });
                },
            },
        });
    },
};

/** « Publier » depuis une notification : publie l'agent, en montrant l'avancement dans la même fenêtre. */
export async function publierAgent(workflowId: number) {
    const groupe = `publication-${workflowId}`;
    const cours = notifier.enCours({ fr: "Publication en cours…", en: "Publishing…" }, { groupe });
    try {
        const { error } = await publishWorkflowApiV1WorkflowWorkflowIdPublishPost({ path: { workflow_id: workflowId } });
        if (error) throw error;
        cours.succes({ fr: "Agent publié.", en: "Agent published." }, { groupe });
    } catch (erreur) {
        cours.echec(
            { fr: "Publication impossible. Réessayez.", en: "Could not publish. Try again." },
            { erreur, reessayer: () => void publierAgent(workflowId), groupe },
        );
    }
}
