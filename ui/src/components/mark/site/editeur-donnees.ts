/**
 * [.mark] V5 : les données de l'éditeur du widget (maquette `editeur-widget.tsx` + `mock-data/site.ts`), branchées sur le
 * schéma réel de l'apparence (`ApparenceWidget`). Rien ici n'est affiché sans donnée réelle derrière.
 *
 * - `COULEURS` : chaque couleur de la maquette (rondFond, boutonTexte…) et la clé réelle qui la porte.
 * - `couleursResolues` : la même règle que le serveur (`ApparenceWidget.couleurs_resolues`) et que le widget public.
 * - `ZONES` : ce qu'on règle en cliquant sur un élément du widget (repères `data-zone` du vrai widget).
 */
import type { ApparenceWidget, TextesWidget } from "@/client/types.gen";

export const BLEU_MARK = "#1b5fb0";
export const FOND_DEFAUT = "#ffffff";
export const TEXTE_DEFAUT = "#0f1c2e";
// Les teintes proposées d'un clic dans la bulle (le bleu .mark d'abord), en plus du choix libre : de la donnée du widget.
export const TEINTES = ["#1b5fb0", "#3d8fe6", "#8fbdf1", "#ffffff", "#f1f1f1", "#1c1917", "#dc2626"];

export type Apparence = ApparenceWidget;
export type CleTexte = keyof TextesWidget;

/** Les couleurs de la maquette, chacune sur sa donnée. `fenetreTexte` est le texte de base de la fenêtre, pas une retouche. */
export const COULEURS = {
    rondFond: "rond_accroche",
    rondTexte: "rond_accroche_texte",
    fenetreFond: "fenetre",
    fenetreTexte: "texte_fenetre",
    orbe: "orbe",
    boutonFond: "boutons",
    boutonTexte: "boutons_texte",
    raccrocherFond: "raccrocher",
    raccrocherTexte: "raccrocher_texte",
    saisieFond: "champ_saisie",
    saisieTexte: "champ_saisie_texte",
    bulleAgentFond: "bulle_agent",
    bulleAgentTexte: "bulle_agent_texte",
    bulleVisiteurFond: "bulles_ecrit",
    bulleVisiteurTexte: "bulles_ecrit_texte",
    etoiles: "etoiles",
    choixFond: "reponses_choisies",
    choixTexte: "reponses_choisies_texte",
    icones: "icones",
} as const;
export type CleCouleur = keyof typeof COULEURS;

// ---- la règle de couleur (miroir de `api/schemas/apparence_widget.py` et de `public/embed/dograh-widget.js`) ----
const luminance = (hex: string) => {
    let n = hex.replace("#", "");
    if (n.length === 3) n = [...n].map((c) => c + c).join("");
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contraste = (a: string, b: string) => {
    const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
    return (x + 0.05) / (y + 0.05);
};
/** Blanc ou presque noir, le plus lisible sur ce fond : une valeur par défaut seulement. */
export const texteSur = (fond: string) => (contraste(fond, "#ffffff") >= contraste(fond, "#111111") ? "#ffffff" : "#111111");

export function couleursResolues(ap: Apparence): Record<CleCouleur, string> {
    const base = ap.couleur_base ?? BLEU_MARK;
    const fond = ap.fond_fenetre ?? FOND_DEFAUT;
    const texte = ap.texte_fenetre ?? TEXTE_DEFAUT;
    const r = (ap.couleurs ?? {}) as Record<string, string | null | undefined>;
    const prend = (cle: string, defaut: string) => r[cle] || defaut;
    const rondFond = prend("rond_accroche", base);
    const boutonFond = prend("boutons", base);
    const bulleVisiteurFond = prend("bulles_ecrit", base);
    const choixFond = prend("reponses_choisies", base);
    return {
        rondFond,
        rondTexte: prend("rond_accroche_texte", texteSur(rondFond)),
        fenetreFond: prend("fenetre", fond),
        fenetreTexte: texte,
        orbe: prend("orbe", base),
        boutonFond,
        boutonTexte: prend("boutons_texte", texteSur(boutonFond)),
        raccrocherFond: prend("raccrocher", "#dc2626"),
        raccrocherTexte: prend("raccrocher_texte", "#ffffff"),
        saisieFond: prend("champ_saisie", fond),
        saisieTexte: prend("champ_saisie_texte", texte),
        bulleAgentFond: prend("bulle_agent", "#f1f1f1"),
        bulleAgentTexte: prend("bulle_agent_texte", texte),
        bulleVisiteurFond,
        bulleVisiteurTexte: prend("bulles_ecrit_texte", texteSur(bulleVisiteurFond)),
        etoiles: prend("etoiles", base),
        choixFond,
        choixTexte: prend("reponses_choisies_texte", texteSur(choixFond)),
        icones: prend("icones", base),
    };
}

/** Pose une couleur : `fenetreTexte` est un champ de base, les autres sont des retouches par élément. */
export function avecCouleur(ap: Apparence, cle: CleCouleur, valeur: string): Apparence {
    if (cle === "fenetreTexte") return { ...ap, texte_fenetre: valeur };
    return { ...ap, couleurs: { ...(ap.couleurs ?? {}), [COULEURS[cle]]: valeur } };
}

export function avecTexte(ap: Apparence, cle: CleTexte, valeur: string): Apparence {
    return { ...ap, textes: { ...(ap.textes ?? {}), [cle]: valeur } };
}

/** « Revenir au bleu .mark » : le bleu, l'orbe, le fond et le texte de base, sans retouche ; les textes ne changent pas. */
export function auBleuMark(ap: Apparence): Apparence {
    return { ...ap, couleur_base: BLEU_MARK, fond_fenetre: FOND_DEFAUT, texte_fenetre: TEXTE_DEFAUT, couleurs: {}, embleme: "orbe" };
}

// ---- bornes du serveur, vérifiées avant d'enregistrer (l'erreur se lit sous le champ) ----
export const ACCROCHE_LIGNES_MAX = 3;
export const ACCROCHE_LONGUEUR_MAX = 120;
export const TEXTE_LONGUEUR_MAX = 200;

export function erreurDeTexte(cle: CleTexte, valeur: string): "vide" | "long" | "lignes" | null {
    if (!valeur.trim()) return "vide";
    if (cle === "accroche") {
        if (valeur.length > ACCROCHE_LONGUEUR_MAX) return "long";
        if (valeur.split("\n").length > ACCROCHE_LIGNES_MAX) return "lignes";
        return null;
    }
    return valeur.length > TEXTE_LONGUEUR_MAX ? "long" : null;
}

export const adresseValide = (v: string | null | undefined) => !v || (v.startsWith("https://") && v.length <= 500);

// ---- les étapes du visiteur ----
export type EtatWidget = "repos" | "accroche" | "information" | "conversation" | "avis" | "merci" | "plafond";
export const ETAPES: { id: EtatWidget; fr: string; en: string }[] = [
    { id: "repos", fr: "Replié", en: "Collapsed" },
    { id: "accroche", fr: "Accroche", en: "Hook" },
    { id: "information", fr: "Information", en: "Information" },
    { id: "conversation", fr: "Conversation", en: "Conversation" },
    { id: "avis", fr: "Avis", en: "Review" },
    { id: "merci", fr: "Merci", en: "Thanks" },
    { id: "plafond", fr: "Plafond atteint", en: "Limit reached" },
];

type Bilingue = { en: string; fr: string };
export type Zone = {
    libelle: Bilingue;
    couleurs?: { cle: CleCouleur; libelle: Bilingue }[];
    textes?: { cle: CleTexte; long?: boolean; libelle?: Bilingue }[];
    aide?: Bilingue;
    embleme?: boolean; // le rond replié : orbe ou logo
    lien?: boolean; // l'information : lien vers la politique de confidentialité
};
const FOND: Bilingue = { fr: "Fond", en: "Background" };
const TEXTE: Bilingue = { fr: "Texte", en: "Text" };
const BOUTONS = [
    { cle: "boutonFond" as const, libelle: FOND },
    { cle: "boutonTexte" as const, libelle: TEXTE },
];
const AIDE_BOUTONS: Bilingue = { fr: "Les boutons du widget partagent ces deux couleurs.", en: "The widget's buttons share these two colours." };
const SAISIE = [
    { cle: "saisieFond" as const, libelle: FOND },
    { cle: "saisieTexte" as const, libelle: TEXTE },
];

/** Chaque élément cliquable du widget (repère `data-zone` du vrai widget) : ce qu'on y règle. */
export const ZONES: Record<string, Zone> = {
    rond: { libelle: { fr: "Le widget replié", en: "The collapsed widget" }, couleurs: [{ cle: "orbe", libelle: { fr: "Orbe", en: "Orb" } }], embleme: true },
    accroche: {
        libelle: { fr: "La carte d'accroche", en: "The hook card" },
        couleurs: [{ cle: "rondFond", libelle: FOND }, { cle: "rondTexte", libelle: TEXTE }],
        textes: [{ cle: "accroche", long: true }],
        aide: { fr: "Un retour à la ligne ici = un retour à la ligne sur le site.", en: "A line break here = a line break on the site." },
    },
    fenetre: { libelle: { fr: "La fenêtre", en: "The window" }, couleurs: [{ cle: "fenetreFond", libelle: FOND }, { cle: "fenetreTexte", libelle: TEXTE }] },
    titre: {
        libelle: { fr: "Le titre de la fenêtre", en: "The window title" },
        textes: [{ cle: "titre" }],
        couleurs: [{ cle: "fenetreTexte", libelle: { fr: "Texte de la fenêtre", en: "Window text" } }],
    },
    orbe: { libelle: { fr: "L'orbe", en: "The orb" }, couleurs: [{ cle: "orbe", libelle: { fr: "Couleur", en: "Colour" } }] },
    information: {
        libelle: { fr: "L'information du visiteur", en: "The visitor information" },
        textes: [{ cle: "annonce_ia", long: true }],
        couleurs: [{ cle: "icones", libelle: { fr: "Icône", en: "Icon" } }],
        lien: true,
    },
    caseConfidentialite: { libelle: { fr: "La case de confidentialité", en: "The privacy checkbox" }, textes: [{ cle: "case_confidentialite", long: true }] },
    caseMicro: { libelle: { fr: "La case du micro", en: "The microphone checkbox" }, textes: [{ cle: "case_micro", long: true }] },
    demarrer: { libelle: { fr: "Le bouton pour démarrer", en: "The start button" }, textes: [{ cle: "bouton_demarrer" }], couleurs: BOUTONS, aide: AIDE_BOUTONS },
    plafond: { libelle: { fr: "Le message du plafond atteint", en: "The limit-reached message" }, textes: [{ cle: "plafond_message", long: true }] },
    plafondBouton: { libelle: { fr: "Le bouton pour être rappelé", en: "The callback button" }, textes: [{ cle: "plafond_bouton" }], couleurs: BOUTONS, aide: AIDE_BOUTONS },
    microRefuse: {
        libelle: { fr: "Le message du micro refusé", en: "The microphone-refused message" },
        textes: [{ cle: "erreur_micro", long: true }],
        couleurs: [{ cle: "icones", libelle: { fr: "Teinte de l'encart", en: "Box tint" } }],
    },
    etatOrbe: {
        libelle: { fr: "Les mentions sous l'orbe", en: "The captions under the orb" },
        textes: [
            { cle: "ecoute", libelle: { fr: "Quand l'assistant écoute", en: "When the assistant listens" } },
            { cle: "reflexion", libelle: { fr: "Quand il réfléchit", en: "When it thinks" } },
            { cle: "parle", libelle: { fr: "Quand il répond", en: "When it answers" } },
        ],
    },
    bulleAgent: { libelle: { fr: "La bulle de l'assistant", en: "The assistant's bubble" }, couleurs: [{ cle: "bulleAgentFond", libelle: FOND }, { cle: "bulleAgentTexte", libelle: TEXTE }] },
    bulleVisiteur: { libelle: { fr: "La bulle du visiteur", en: "The visitor's bubble" }, couleurs: [{ cle: "bulleVisiteurFond", libelle: FOND }, { cle: "bulleVisiteurTexte", libelle: TEXTE }] },
    raccrocher: {
        libelle: { fr: "Le bouton pour raccrocher", en: "The hang-up button" },
        textes: [{ cle: "raccrocher" }],
        couleurs: [{ cle: "raccrocherFond", libelle: FOND }, { cle: "raccrocherTexte", libelle: { fr: "Icône", en: "Icon" } }],
        aide: { fr: "Ce texte n'est pas affiché : il est lu par les lecteurs d'écran et apparaît au survol.", en: "This text is not displayed: screen readers read it and it shows on hover." },
    },
    saisieVoix: { libelle: { fr: "Le champ de saisie", en: "The input field" }, textes: [{ cle: "champ_saisie" }], couleurs: SAISIE },
    saisieEcrite: { libelle: { fr: "Le champ de la conversation écrite", en: "The written-conversation field" }, textes: [{ cle: "ecrire" }], couleurs: SAISIE },
    envoyer: { libelle: { fr: "Le bouton d'envoi", en: "The send button" }, textes: [{ cle: "envoyer" }], couleurs: BOUTONS, aide: AIDE_BOUTONS },
    avisTitre: { libelle: { fr: "Le titre de l'avis", en: "The review title" }, textes: [{ cle: "avis_titre" }] },
    avisQuestion: { libelle: { fr: "La question de l'avis", en: "The review question" }, textes: [{ cle: "avis_question" }] },
    etoiles: { libelle: { fr: "Les étoiles", en: "The stars" }, couleurs: [{ cle: "etoiles", libelle: { fr: "Couleur", en: "Colour" } }] },
    choix: { libelle: { fr: "Les réponses de l'avis", en: "The review answers" }, couleurs: [{ cle: "choixFond", libelle: { fr: "Réponse choisie", en: "Chosen answer" } }, { cle: "choixTexte", libelle: { fr: "Son texte", en: "Its text" } }] },
    caseRappel: { libelle: { fr: "La case pour être rappelé (note de 1 à 3)", en: "The callback checkbox (rating 1 to 3)" }, textes: [{ cle: "case_rappel" }] },
    casePublication: { libelle: { fr: "La case pour afficher l'avis (note de 4 ou 5)", en: "The publish checkbox (rating 4 or 5)" }, textes: [{ cle: "case_publication" }] },
    avisPasser: { libelle: { fr: "Le bouton pour passer", en: "The skip button" }, textes: [{ cle: "avis_passer" }] },
    avisEnvoyer: { libelle: { fr: "Le bouton pour envoyer l'avis", en: "The send-review button" }, textes: [{ cle: "avis_envoyer" }], couleurs: BOUTONS, aide: AIDE_BOUTONS },
    merciIcone: { libelle: { fr: "L'icône de fin", en: "The end icon" }, couleurs: BOUTONS, aide: AIDE_BOUTONS },
    merci: { libelle: { fr: "Le message de fin", en: "The end message" }, textes: [{ cle: "merci" }] },
    fermer: { libelle: { fr: "Le bouton pour fermer", en: "The close button" }, textes: [{ cle: "fermer" }] },
};
// Le champ d'envoi de la conversation vocale porte le repère `envoyerVoix` dans le widget : même réglage que « envoyer ».
ZONES.envoyerVoix = ZONES.envoyer;

export const POLICES: { id: NonNullable<Apparence["police"]>; fr: string; en: string; famille: string }[] = [
    { id: "site", fr: "Celle de votre site", en: "Your site's", famille: "inherit" },
    { id: "switzer", fr: "Switzer (celle de .mark)", en: "Switzer (.mark's)", famille: "'Mark Switzer', system-ui, sans-serif" },
    { id: "inter", fr: "Inter", en: "Inter", famille: "Inter, system-ui, sans-serif" },
    { id: "systeme", fr: "Celle de l'appareil", en: "The device's", famille: "system-ui, sans-serif" },
    // S-1 : les six polices de la maquette, hébergées chez nous (fichiers `.woff2` déposés dans `ui/public/embed/fonts/`).
    { id: "poppins", fr: "Poppins", en: "Poppins", famille: "'Mark Poppins', system-ui, sans-serif" },
    { id: "montserrat", fr: "Montserrat", en: "Montserrat", famille: "'Mark Montserrat', system-ui, sans-serif" },
    { id: "lato", fr: "Lato", en: "Lato", famille: "'Mark Lato', system-ui, sans-serif" },
    { id: "nunito", fr: "Nunito", en: "Nunito", famille: "'Mark Nunito', system-ui, sans-serif" },
    { id: "dm-sans", fr: "DM Sans", en: "DM Sans", famille: "'Mark DM Sans', system-ui, sans-serif" },
    { id: "playfair-display", fr: "Playfair Display", en: "Playfair Display", famille: "'Mark Playfair Display', Georgia, serif" },
];

export type Declenchement = "survol" | "delai" | "toujours" | "jamais";
export const DECLENCHEMENTS: { id: Declenchement; fr: string; en: string }[] = [
    { id: "delai", fr: "Après quelques secondes", en: "After a few seconds" },
    { id: "survol", fr: "Au survol du rond", en: "On hover of the circle" },
    { id: "toujours", fr: "Toujours affichée", en: "Always shown" },
    { id: "jamais", fr: "Jamais (le rond seul)", en: "Never (the circle alone)" },
];
/** « clic » est l'ancienne valeur du survol : l'éditeur la montre comme « survol » et écrit « survol ». */
export const declenchementDe = (ap: Apparence): Declenchement => (ap.declenchement === "clic" || !ap.declenchement ? "survol" : ap.declenchement);
