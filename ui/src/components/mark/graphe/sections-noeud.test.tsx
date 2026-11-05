/**
 * [.mark] La fenêtre d'un nœud à onglets par sujet (E15).
 *
 * Questions de ce fichier :
 *
 *     Chaque type de nœud montre-t-il seulement les onglets dont il porte les champs ? Aucune propriété du fork ne
 *     se perd-elle (chacune est dans exactement un onglet, le nom en tête) ? L'onglet choisi change-t-il le volet
 *     montré sans démonter les autres ?
 *
 * Les listes de propriétés sont celles que le serveur sert (`all_specs()` du fork, relevées le 03/11/2026).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OngletsNoeud } from "./OngletsNoeud";
import { proprietesDeLaSection, sectionDeLaPropriete, type SectionNoeud, sectionsAMontrer } from "./sections-noeud";

afterEach(cleanup);

const SPECS: Record<string, string[]> = {
    agentNode: ["name", "prompt", "premiere_replique", "champs_etape", "qui_decide_du_passage", "moment_du_passage", "delai_du_passage", "arbitre", "seuil_de_l_arbitre", "passation_par_le_code", "allow_interrupt", "add_global_prompt", "extraction_enabled", "extraction_prompt", "extraction_variables", "tool_uuids", "document_uuids"],
    endCall: ["name", "prompt", "premiere_replique", "add_global_prompt", "extraction_enabled", "extraction_prompt", "extraction_variables"],
    globalNode: ["name", "prompt"],
    noveum: ["name", "noveum_enabled", "noveum_api_key", "noveum_project", "noveum_environment", "noveum_record_audio"],
    paygent: ["name", "paygent_enabled", "paygent_api_key", "paygent_agent_id", "paygent_customer_id", "paygent_indicator"],
    qa: ["name", "qa_enabled", "qa_system_prompt", "qa_min_call_duration", "qa_voicemail_calls", "qa_sample_rate", "qa_use_workflow_llm", "qa_provider", "qa_model", "qa_api_key", "qa_endpoint"],
    startCall: ["name", "greeting_type", "greeting", "greeting_recording_id", "prompt", "champs_etape", "qui_decide_du_passage", "moment_du_passage", "delai_du_passage", "arbitre", "seuil_de_l_arbitre", "passation_par_le_code", "allow_interrupt", "add_global_prompt", "delayed_start", "delayed_start_duration", "extraction_enabled", "extraction_prompt", "extraction_variables", "tool_uuids", "document_uuids", "pre_call_fetch_mode", "pre_call_fetch_url", "pre_call_fetch_credential_uuid", "pre_call_fetch_remplace"],
    trigger: ["name", "enabled", "trigger_path"],
    tuner: ["name", "tuner_enabled", "tuner_agent_id", "tuner_workspace_id", "tuner_api_key", "cost_calculation_enabled", "cost_llm_input_rate", "cost_llm_cached_input_rate", "cost_llm_output_rate", "cost_tts_rate", "cost_stt_rate", "cost_telephony_rate"],
    webhook: ["name", "enabled", "http_method", "endpoint_url", "credential_uuid", "custom_headers", "payload_template"],
};

describe("les onglets de chaque type de nœud", () => {
    it("une étape d'agent : Conversation, Données, Outils, Passage (et les blocs Agents, Garde-fous, Phrases quand ils s'appliquent)", () => {
        expect(sectionsAMontrer(SPECS.agentNode, [])).toEqual(["conversation", "donnees", "outils", "passage"]);
        expect(sectionsAMontrer(SPECS.agentNode, ["outils", "agents", "garde", "phrases"])).toEqual([
            "conversation",
            "donnees",
            "outils",
            "passage",
            "agents",
            "garde",
            "phrases",
        ]);
    });

    it("le départ a de plus « Avant l'appel » ; la fin n'a ni Passage ni Outils", () => {
        expect(sectionsAMontrer(SPECS.startCall, [])).toEqual(["conversation", "avant", "donnees", "outils", "passage"]);
        expect(sectionsAMontrer(SPECS.endCall, [])).toEqual(["conversation", "donnees"]);
        expect(sectionsAMontrer(SPECS.endCall, ["phrases"])).toEqual(["conversation", "donnees", "phrases"]);
    });

    it("le prompt général n'a que Conversation ; le déclencheur et le webhook que Requête ; le contrôle qualité que Analyse", () => {
        expect(sectionsAMontrer(SPECS.globalNode, [])).toEqual(["conversation"]);
        expect(sectionsAMontrer(SPECS.trigger, ["requete"])).toEqual(["requete"]);
        expect(sectionsAMontrer(SPECS.webhook, [])).toEqual(["requete"]);
        expect(sectionsAMontrer(SPECS.qa, [])).toEqual(["analyse"]);
    });

    it("un nœud d'intégration (propriétés inconnues du tableau) n'a que « Général » : rien ne se perd", () => {
        for (const type of ["noveum", "paygent", "tuner"]) {
            expect(sectionsAMontrer(SPECS[type], [])).toEqual(["general"]);
        }
    });

    it("n'affiche que les propriétés visibles : un champ masqué par les options d'affichage ne crée pas son onglet", () => {
        // Sans « extraction_enabled », ses trois champs sont masqués : l'onglet Données disparaît de la fin.
        const visibles = SPECS.endCall.filter((n) => !n.startsWith("extraction_") || n === "extraction_enabled");
        expect(sectionsAMontrer(visibles, [])).toEqual(["conversation", "donnees"]);
        const sans = SPECS.endCall.filter((n) => !n.startsWith("extraction_"));
        expect(sectionsAMontrer(sans, [])).toEqual(["conversation"]);
    });
});

describe("aucune propriété ne se perd", () => {
    it("chaque propriété de chaque type est dans exactement un onglet, le nom étant en tête de la fenêtre", () => {
        for (const [type, proprietes] of Object.entries(SPECS)) {
            const sections = sectionsAMontrer(proprietes, []);
            const placees = sections.flatMap((s) => proprietesDeLaSection(proprietes, s));
            expect([...placees].sort(), type).toEqual(proprietes.filter((n) => n !== "name").sort());
            expect(new Set(placees).size, type).toBe(placees.length);
        }
    });

    it("le rangement des propriétés connues est celui du plan (E15)", () => {
        const attendu: Record<string, SectionNoeud> = {
            prompt: "conversation",
            greeting: "conversation",
            pre_call_fetch_url: "avant",
            pre_call_fetch_remplace: "avant",
            extraction_variables: "donnees",
            champs_etape: "donnees",
            tool_uuids: "outils",
            document_uuids: "outils",
            moment_du_passage: "passage",
            seuil_de_l_arbitre: "passage",
            passation_par_le_code: "passage",
            endpoint_url: "requete",
            qa_model: "analyse",
            une_propriete_inconnue: "general",
        };
        for (const [nom, section] of Object.entries(attendu)) expect(sectionDeLaPropriete(nom), nom).toBe(section);
    });
});

describe("la ligne d'onglets", () => {
    const sections: { id: SectionNoeud; contenu: React.ReactNode }[] = [
        { id: "conversation", contenu: <p>Texte du prompt</p> },
        { id: "outils", contenu: <p>Liste des outils</p> },
    ];

    it("montre un onglet par section, la première active, et le nom en tête", () => {
        render(<OngletsNoeud entete={<p>Nom du nœud</p>} sections={sections} />);
        const onglets = screen.getAllByRole("tab");
        expect(onglets.map((o) => o.getAttribute("data-section"))).toEqual(["conversation", "outils"]);
        expect(onglets[0].getAttribute("aria-selected")).toBe("true");
        expect(screen.getByText("Nom du nœud")).toBeTruthy();
    });

    it("change de volet au clic, sans démonter l'autre (le brouillon d'un bloc ne se perd pas)", () => {
        render(<OngletsNoeud sections={sections} />);
        const volet = (id: string) => document.querySelector(`[data-volet="${id}"]`) as HTMLElement;
        expect(volet("conversation").hidden).toBe(false);
        expect(volet("outils").hidden).toBe(true);
        fireEvent.click(screen.getByRole("tab", { name: "Tools" }));
        expect(volet("conversation").hidden).toBe(true);
        expect(volet("outils").hidden).toBe(false);
        expect(volet("conversation").textContent).toContain("Texte du prompt");
    });

    it("une seule section : pas de ligne d'onglets", () => {
        render(<OngletsNoeud sections={[sections[0]]} />);
        expect(screen.queryAllByRole("tab")).toHaveLength(0);
        expect(screen.getByText("Texte du prompt")).toBeTruthy();
    });
});
