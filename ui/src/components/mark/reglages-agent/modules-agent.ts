/**
 * [.mark] cloture-code, F8 (M4): the agent's modules as the page draws them, one sub-menu each.
 *
 * The declaration lives in the fork's registry (`api/services/modules/registre.py`); this list says which
 * of the agent's keys each sub-menu holds, in the registry's order. `modules-ecran.test.tsx` reads the
 * registry's codes and `CLES_THEME_MODULES` (`api/services/groupe/reglages.py`) and fails if this list
 * drifts from them. What depends on the organization (the translator plugged in for each need, a
 * module switched on by its tools) comes from `GET /agents/{id}/modules`.
 */
import type { Texte } from "../langue/langue";

export interface ModuleAgent {
    code: string;
    titre: Texte;
    /** The agent's key that switches it on; `null`: on when a step carries one of its tools. */
    interrupteur: string | null;
    /** Its other keys, shown only with the switch on (E8, as in the theme they came from). */
    reglages: string[];
}

export const MODULES_AGENT: ModuleAgent[] = [
    {
        code: "nombres",
        titre: { en: "Numbers and references", fr: "Nombres et références" },
        interrupteur: "conversion_nombres_transcription",
        reglages: ["variables_reference"],
    },
    {
        code: "communes_et_voies",
        titre: { en: "Town and street", fr: "Commune et rue" },
        interrupteur: "verification_communes",
        reglages: ["variables_commune", "sons_communes", "verification_voies"],
    },
    { code: "epellation", titre: { en: "Spelling", fr: "Épellation" }, interrupteur: "lecture_epellation", reglages: [] },
    {
        code: "lexique",
        titre: { en: "Trade vocabulary", fr: "Lexique métier" },
        interrupteur: "lexique_metier",
        reglages: ["sons_lexique"],
    },
    // [.mark] Module Restauration, lots 4 et 5 : la recherche dans une liste fermée, puis la commande sur catalogue (ordre du registre).
    {
        code: "recherche_liste",
        titre: { en: "Search in a closed list", fr: "Recherche dans une liste" },
        interrupteur: "recherche_dans_une_liste",
        reglages: ["recherche_liste_seuil_retenu", "recherche_liste_seuil_ambigu", "recherche_liste_son", "recherche_liste_sens"],
    },
    {
        code: "commande",
        titre: { en: "Order on a catalogue", fr: "Commande sur catalogue" },
        interrupteur: "commande_sur_catalogue",
        reglages: [
            "commande_ordre_impose",
            "commande_relecture_deux_temps",
            "commande_vente_en_plus",
            "commande_notes_libres",
            "commande_mentions_de_remise",
            "commande_moities_prix",
        ],
    },
    {
        code: "controle_des_donnees",
        titre: { en: "Field recognition", fr: "Reconnaissance des champs" },
        interrupteur: "controle_donnees",
        reglages: ["variables_telephone", "variables_code_postal", "variables_courriel", "variables_date"],
    },
    { code: "equipe", titre: { en: "Team and transfers", fr: "Équipe et transferts" }, interrupteur: "equipe_connue", reglages: [] },
    {
        code: "verification_appelant",
        titre: { en: "Caller verification", fr: "Vérification de l'appelant" },
        interrupteur: "verification_appelant",
        reglages: [],
    },
    { code: "planificateur", titre: { en: "Appointment planner", fr: "Planificateur de rendez-vous" }, interrupteur: null, reglages: [] },
];

/** Every agent key the modules own, in order. */
export const CLES_MODULES: string[] = MODULES_AGENT.flatMap((m) => [...(m.interrupteur ? [m.interrupteur] : []), ...m.reglages]);

/** The module that holds a key (to open its sub-menu on « show », E7). */
export const moduleDeLaCle = (cle: string): ModuleAgent | undefined =>
    MODULES_AGENT.find((m) => m.interrupteur === cle || m.reglages.includes(cle));
