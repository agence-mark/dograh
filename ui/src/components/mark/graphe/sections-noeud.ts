/**
 * [.mark] La fenêtre d'un nœud à onglets par sujet (E15) : Conversation · Avant l'appel · Données · Outils · Passage ·
 * Agents · Garde-fous · Phrases · Requête · Analyse. Un onglet n'existe que si le type de nœud porte des champs ou des
 * blocs de ce sujet. Pur : le rangement d'une propriété du fork dans un sujet, et la liste des onglets à montrer.
 *
 * Aucune propriété ne se perd : celle que ce tableau ne connaît pas va dans « Général » (un nœud d'intégration n'a que
 * celui-là, et la ligne d'onglets disparaît quand il n'y en a qu'un). Le nom du nœud n'est dans aucun onglet : il reste
 * en tête de la fenêtre.
 */
import type { Texte } from "@/components/mark/langue/langue";

export type SectionNoeud =
    | "conversation"
    | "avant"
    | "donnees"
    | "outils"
    | "passage"
    | "agents"
    | "garde"
    | "phrases"
    | "requete"
    | "analyse"
    | "general";

export const ORDRE_DES_SECTIONS: SectionNoeud[] = [
    "conversation",
    "avant",
    "donnees",
    "outils",
    "passage",
    "agents",
    "garde",
    "phrases",
    "requete",
    "analyse",
    "general",
];

export const TITRES_DES_SECTIONS: Record<SectionNoeud, Texte> = {
    conversation: { en: "Conversation", fr: "Conversation" },
    avant: { en: "Before the call", fr: "Avant l'appel" },
    donnees: { en: "Data", fr: "Données" },
    outils: { en: "Tools", fr: "Outils" },
    passage: { en: "Hand-over", fr: "Passage" },
    agents: { en: "Agents", fr: "Agents" },
    garde: { en: "Safeguards", fr: "Garde-fous" },
    phrases: { en: "Sentences", fr: "Phrases" },
    requete: { en: "Request", fr: "Requête" },
    analyse: { en: "Analysis", fr: "Analyse" },
    general: { en: "General", fr: "Général" },
};

/** Le nom du nœud : toujours en tête de la fenêtre, jamais dans un onglet. */
export const PROPRIETE_DU_NOM = "name";

const PAR_PROPRIETE: Record<string, SectionNoeud> = {
    prompt: "conversation",
    premiere_replique: "conversation",
    greeting_type: "conversation",
    greeting: "conversation",
    greeting_recording_id: "conversation",
    allow_interrupt: "conversation",
    add_global_prompt: "conversation",
    delayed_start: "conversation",
    delayed_start_duration: "conversation",
    pre_call_fetch_mode: "avant",
    pre_call_fetch_url: "avant",
    pre_call_fetch_credential_uuid: "avant",
    pre_call_fetch_remplace: "avant",
    champs_etape: "donnees",
    extraction_enabled: "donnees",
    extraction_prompt: "donnees",
    extraction_variables: "donnees",
    tool_uuids: "outils",
    document_uuids: "outils",
    qui_decide_du_passage: "passage",
    moment_du_passage: "passage",
    delai_du_passage: "passage",
    arbitre: "passage",
    seuil_de_l_arbitre: "passage",
    passation_par_le_code: "passage",
    enabled: "requete",
    trigger_path: "requete",
    http_method: "requete",
    endpoint_url: "requete",
    credential_uuid: "requete",
    custom_headers: "requete",
    payload_template: "requete",
};

/** Le sujet d'une propriété du fork. Les réglages du contrôle qualité (`qa_*`) sont l'onglet Analyse. */
export function sectionDeLaPropriete(nom: string): SectionNoeud {
    if (nom.startsWith("qa_")) return "analyse";
    return PAR_PROPRIETE[nom] ?? "general";
}

/**
 * Les onglets à montrer, dans l'ordre : ceux qui ont au moins une propriété visible (`proprietesVisibles`, déjà
 * filtrées par les options d'affichage) ou un bloc (`blocs`, les sujets des blocs .mark que le type de nœud porte).
 */
export function sectionsAMontrer(proprietesVisibles: string[], blocs: SectionNoeud[]): SectionNoeud[] {
    const presentes = new Set<SectionNoeud>(blocs);
    for (const nom of proprietesVisibles) {
        if (nom !== PROPRIETE_DU_NOM) presentes.add(sectionDeLaPropriete(nom));
    }
    return ORDRE_DES_SECTIONS.filter((s) => presentes.has(s));
}

/** L'ordre des champs de l'onglet Conversation, comme la maquette : le prompt d'abord, puis l'accueil, puis les interrupteurs. */
const ORDRE_CONVERSATION = Object.keys(PAR_PROPRIETE).filter((nom) => PAR_PROPRIETE[nom] === "conversation");

/** Les propriétés (visibles) d'un onglet. */
export const proprietesDeLaSection = (proprietesVisibles: string[], section: SectionNoeud): string[] => {
    const noms = proprietesVisibles.filter((nom) => nom !== PROPRIETE_DU_NOM && sectionDeLaPropriete(nom) === section);
    if (section !== "conversation") return noms;
    const rang = (nom: string) => (ORDRE_CONVERSATION.includes(nom) ? ORDRE_CONVERSATION.indexOf(nom) : ORDRE_CONVERSATION.length);
    return noms.map((nom, i) => ({ nom, i })).sort((a, b) => rang(a.nom) - rang(b.nom) || a.i - b.i).map(({ nom }) => nom);
};

/**
 * Les champs d'un nœud qu'on ne montre pas, par type (05 § 17).
 * - Sur l'étape de départ, « L'appelant peut couper la parole » est masqué : la protection de l'accueil de l'agent l'annule ; seul
 *   « L'appelant peut couper l'accueil » (réglage de l'agent) reste.
 * - Sur une fin d'appel d'un agent principal qui porte ses fins, le prompt n'est pas écrit à la main.
 */
export const proprietesMasquees = (type: string, etape: { estPrincipal?: boolean; fins?: unknown }): string[] => [
    ...(type === "endCall" && etape.estPrincipal && Array.isArray(etape.fins) && etape.fins.length > 0 ? ["prompt"] : []),
    ...(type === "startCall" ? ["allow_interrupt"] : []),
];
