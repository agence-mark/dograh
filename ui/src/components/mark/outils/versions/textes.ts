/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : les textes des versions d'outils, en français et en anglais.
 * La règle se dit UNE fois, en bulle ; elle n'est écrite en dur nulle part ailleurs.
 */
import type { Texte } from "../../langue/langue";

export const REGLE_VERSIONS_OUTIL: Texte = {
    fr: "Enregistrer un outil modifié crée une nouvelle version. Un agent reste toujours sur la version de ses outils figée par sa version publiée : il ne suit jamais seul une nouvelle version, parce qu'un outil touche un vrai logiciel. On passe à la nouvelle à la main, agent par agent et branche par branche : le bouton écrit dans le brouillon de l'agent, puis on teste et on publie comme d'habitude.",
    en: "Saving a changed tool creates a new version. An agent always stays on the version of its tools frozen by its published version: it never follows a new version on its own, because a tool touches real software. You move to the new one by hand, agent by agent and branch by branch: the button writes into the agent's draft, then you test and publish as usual.",
};

export const T = {
    passerA: (n: number): Texte => ({ fr: `Passer à la v${n}`, en: `Move to v${n}` }),
    titreConfirmation: (n: number): Texte => ({ fr: `Passer à la v${n} ?`, en: `Move to v${n}?` }),
    description: { fr: "Confirmer le passage de l'agent à la nouvelle version de l'outil", en: "Confirm moving the agent to the tool's new version" },
    corps: (outil: string, de: number, vers: number, agent: string, branche: string): Texte =>
        agent
            ? {
                  fr: `${outil} passe de la v${de} à la v${vers} pour « ${agent} », branche ${branche}.`,
                  en: `${outil} moves from v${de} to v${vers} for “${agent}”, branch ${branche}.`,
              }
            : {
                  fr: `${outil} passe de la v${de} à la v${vers} pour cet agent, sur la branche ouverte.`,
                  en: `${outil} moves from v${de} to v${vers} for this agent, on the open branch.`,
              },
    corpsAide: (de: number): Texte => ({
        fr: `Cela s'écrit dans le brouillon de l'agent : rien n'est publié, les appels en cours gardent la v${de}. À tester, puis à publier comme d'habitude.`,
        en: `This is written into the agent's draft: nothing is published, calls in progress keep v${de}. Test it, then publish as usual.`,
    }),
    annuler: { fr: "Annuler", en: "Cancel" },
    ecrite: (outil: string, n: number, agent: string, branche: string): Texte =>
        agent
            ? {
                  fr: `${outil} v${n} écrite dans le brouillon de « ${agent} » (${branche}). À tester, puis publier.`,
                  en: `${outil} v${n} written into the draft of “${agent}” (${branche}). Test it, then publish.`,
              }
            : {
                  fr: `${outil} v${n} écrite dans le brouillon de l'agent. À tester, puis publier.`,
                  en: `${outil} v${n} written into the agent's draft. Test it, then publish.`,
              },
    echec: { fr: "Le passage n'a pas abouti. Réessayez.", en: "The move did not work. Try again." },
    uneExiste: (n: number): Texte => ({ fr: `une v${n} existe`, en: `a v${n} exists` }),
    dansLeBrouillon: { fr: "dans le brouillon, à tester puis publier", en: "in the draft, to test then publish" },
    dansLeBrouillonCourt: { fr: "dans le brouillon", en: "in the draft" },
    retard: (n: number): Texte =>
        n > 1
            ? { fr: `${n} agents restent sur la version précédente`, en: `${n} agents stay on the previous version` }
            : { fr: "1 agent reste sur la version précédente", en: "1 agent stays on the previous version" },
    derniere: { fr: "dernière", en: "latest" },
    aucunAgent: { fr: "Aucun agent n'est sur cette version.", en: "No agent is on this version." },
    colAgent: { fr: "Agent", en: "Agent" },
    colBranche: { fr: "Branche", en: "Branch" },
    chargement: { fr: "Chargement…", en: "Loading…" },
    erreurLecture: { fr: "Les versions n'ont pas pu être lues. Réessayez.", en: "The versions could not be read. Try again." },
    aucuneVersion: { fr: "Aucune version enregistrée.", en: "No version saved." },
    versionDe: (n: number): Texte => ({ fr: `Version ${n}`, en: `Version ${n}` }),
    outilsAJourTitre: { fr: "Les outils sont à jour", en: "The tools are up to date" },
    outilsAJourSource: {
        fr: "Une version plus récente d'un outil de l'agent existe : l'agent reste sur la sienne tant qu'on ne passe pas à la nouvelle dans le brouillon.",
        en: "A newer version of one of the agent's tools exists: the agent stays on its own until you move to the new one in the draft.",
    },
} satisfies Record<string, Texte | ((...args: never[]) => Texte)>;
