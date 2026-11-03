/**
 * [.mark] V1b : les pièces de la page d'une conversation à la forme de la maquette.
 *
 * Questions de ce fichier :
 *
 *     La transcription se choisit-elle tour par tour, et la colonne de droite dit-elle les étapes du tour choisi
 *     (durées entre jalons) ? Le résumé est-il nu, sans note en dur ? Le journal des événements dit-il une heure et une
 *     phrase par événement, sans texte brut d'erreur ? Le lecteur dit-il « aucun enregistrement » quand il n'y en a pas ?
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AnalyseDuRun } from "@/components/mark/fenetre-du-run/types";
import { FournisseurLangue } from "@/components/mark/langue/langue";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@/client", () => ({ getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { id: "u" } }) }));
vi.mock("@/lib/files", () => ({ getSignedUrl: vi.fn(async () => null), downloadFile: vi.fn() }));
vi.mock("@/components/mark/fenetre-du-run/SectionApresAppel", () => ({
    SectionApresAppel: () => <div data-testid="apres-appel" />,
}));

const { etapesDuTour, VueTranscription } = await import("@/components/mark/fenetre-du-run/FenetreDuRun");
const { JournalDesEvenements, heureDuJournal, phraseDeLEvenement } = await import("./JournalDesEvenements");
const { LecteurConversation } = await import("./LecteurConversation");
const { titreDeLaConversation } = await import("./titre");

afterEach(cleanup);

const enFrancais = (ui: ReactNode) =>
    render(
        <FournisseurLangue>
            <TooltipProvider>{ui}</TooltipProvider>
        </FournisseurLangue>,
    );

const ANALYSE = {
    version: 1,
    run_id: 7,
    summary: {
        status: "ok",
        agent_id: 1,
        definition_id: 1,
        channel: "phone",
        duration_secs: 151,
        disposition: "Demande enregistrée",
        cost: { status: "not_captured" },
        version: { status: "not_captured" },
        incident_count: 0,
    },
    latency: {
        status: "ok",
        turns: [
            { turn: 1, step: "Accueil", measured: true, not_measured_reason: null, end_of_turn_wait_secs: 0.3, transcription_secs: 0.2, passes: [], voice_secs: 0.1, silence_secs: 0.84, slow: false, step_change: false },
            { turn: 2, step: "Dépannage", measured: true, not_measured_reason: null, end_of_turn_wait_secs: 0.3, transcription_secs: 0.2, passes: [], voice_secs: 0.1, silence_secs: 2.8, slow: true, step_change: false },
        ],
    },
    providers: { status: "not_captured" },
    reading_modules: { status: "not_captured" },
    record: {
        status: "ok",
        fields: [
            { name: "nom", value: "Martin", empty: false, declared: true, sure: true, source: "noté", written_at_caller_turn: 1, history: [] },
            { name: "commune", value: null, empty: true, declared: true, sure: null, source: null, written_at_caller_turn: null, history: [] },
        ],
        refusals: [],
    },
    path: { status: "not_captured" },
    conversation: {
        status: "ok",
        lines: [
            { turn: 1, speaker: "agent", text: "Bonjour, je vous écoute.", start_secs: 1, end_secs: 3 },
            { turn: 2, speaker: "caller", text: "Ma chaudière ne démarre plus.", start_secs: 4, end_secs: 6 },
            { turn: 2, speaker: "agent", text: "C'est noté pour jeudi.", start_secs: 7, end_secs: 9 },
        ],
    },
    incidents: { status: "ok", items: [{ turn: 2, kind: "silence_after_tool", fatal: true, processor: null, detail: null }] },
    chrono: {
        status: "ok",
        turns: [
            { turn: 1, step: "Accueil", measured: true, not_measured_reason: null, passes: 1, stages: { turn_closed: 0.3, request_sent: 0.35, first_model_word: 0.65, first_sentence: 0.8, sent_to_voice: 0.82, first_sound: 1 } },
            { turn: 2, step: "Dépannage", measured: true, not_measured_reason: null, passes: 1, stages: { turn_closed: 0.5, request_sent: 0.6, first_model_word: 2.0, first_sentence: 2.5, sent_to_voice: 2.6, first_sound: 2.8 } },
        ],
    },
} as unknown as AnalyseDuRun;

describe("les durées de chaque étape d'un tour", () => {
    it("sont les écarts entre deux jalons du chronomètre, le premier étant l'attente de fin de tour", () => {
        const etapes = etapesDuTour(ANALYSE.chrono!.turns![0].stages);
        expect(etapes.map((e) => e.cle)).toEqual(["turn_closed", "request_sent", "first_model_word", "first_sentence", "sent_to_voice", "first_sound"]);
        expect(etapes.map((e) => Number(e.secs!.toFixed(2)))).toEqual([0.3, 0.05, 0.3, 0.15, 0.02, 0.18]);
    });

    it("un jalon absent reste vide, sans fausser le suivant", () => {
        const etapes = etapesDuTour({ turn_closed: 0.4, request_sent: null, first_model_word: 1.0, first_sentence: null, sent_to_voice: null, first_sound: 1.5 });
        expect(etapes[1].secs).toBeNull();
        expect(Number(etapes[2].secs!.toFixed(2))).toBe(0.6);
    });
});

describe("la vue de la Transcription", () => {
    const vue = () => enFrancais(<VueTranscription workflowId={1} runId={7} lue={{ analyse: ANALYSE, erreur: null }} />);

    it("montre la transcription à gauche et, à droite, le tour le plus lent, la fiche et l'après-appel", () => {
        vue();
        expect(screen.getAllByTestId("ligne-de-conversation")).toHaveLength(3);
        const colonne = screen.getByTestId("colonne-de-droite");
        expect(within(colonne).getByTestId("colonne-tour").textContent).toContain("Ce tour, étape par étape");
        // Tour 2 (lent) : l'attente de fin de tour dure 0,50 s.
        expect(within(colonne).getByTestId("colonne-tour").textContent).toContain("0.50 s");
        expect(within(colonne).getByTestId("colonne-fiche").textContent).toContain("Martin");
        expect(within(colonne).getByTestId("colonne-fiche").textContent).not.toContain("commune");
        expect(within(colonne).getByTestId("apres-appel")).toBeTruthy();
    });

    it("choisir une autre réplique change le tour de la colonne de droite", () => {
        vue();
        const lignes = screen.getAllByTestId("ligne-de-conversation");
        expect(lignes[2].getAttribute("aria-pressed")).toBe("true");
        fireEvent.click(lignes[0]);
        expect(lignes[0].getAttribute("aria-pressed")).toBe("true");
        expect(lignes[2].getAttribute("aria-pressed")).toBe("false");
        // Tour 1 : l'attente de fin de tour dure 0,30 s.
        expect(screen.getByTestId("colonne-tour").textContent).toContain("0.30 s");
    });

    it("dit la latence de la réponse sur la ligne de l'agent, en rouge quand elle est lente", () => {
        vue();
        const lignes = screen.getAllByTestId("ligne-de-conversation");
        expect(lignes[0].textContent).toContain("0.84 s");
        expect(lignes[2].textContent).toContain("2.80 s");
        expect(lignes[1].textContent).not.toContain("2.80 s");
    });

    it("le résumé est nu : aucune carte, aucune note en dur (la précision va dans un « ! »)", () => {
        vue();
        const resume = screen.getByTestId("bloc-summary");
        expect(resume.querySelector("[class*='rounded-xl']")).toBeNull();
        expect(resume.textContent).not.toContain("non captée (run antérieur");
        expect(resume.textContent).not.toContain("pas de table des prix");
        expect(within(resume).getAllByRole("button", { name: "Précision" }).length).toBeGreaterThanOrEqual(1);
    });

    it("une analyse en erreur le dit, une analyse qui charge le dit", () => {
        enFrancais(<VueTranscription workflowId={1} runId={7} lue={{ analyse: null, erreur: "boom" }} />);
        expect(screen.getByRole("alert").textContent).toContain("Analyse du run indisponible");
        cleanup();
        enFrancais(<VueTranscription workflowId={1} runId={7} lue={{ analyse: null, erreur: null }} />);
        expect(screen.getByTestId("fenetre-du-run-chargement")).toBeTruthy();
    });
});

describe("le titre « Motif · Issue »", () => {
    it("lit le motif (motif_appel puis motif) et l'issue de l'appel", () => {
        expect(titreDeLaConversation({ motif_appel: "Dépannage", mapped_call_disposition: "Demande enregistrée" }, "Agent 1")).toBe("Dépannage · Demande enregistrée");
        expect(titreDeLaConversation({ motif: "Devis" }, "Agent 1")).toBe("Devis");
        expect(titreDeLaConversation({ mapped_call_disposition: "Transfert" }, "Agent 1")).toBe("Transfert");
    });

    it("retombe sur le nom de l'agent quand rien n'est écrit (un champ vide ne compte pas)", () => {
        expect(titreDeLaConversation({ motif_appel: "  ", mapped_call_disposition: "" }, "Agent 1")).toBe("Agent 1");
        expect(titreDeLaConversation(null, "Agent 1")).toBe("Agent 1");
    });
});

describe("le journal des événements", () => {
    const t = (x: { en: string; fr: string }) => x.fr;
    const evt = (type: string, payload: Record<string, unknown>, timestamp: string) => ({ type, payload, timestamp, turn: 0 }) as never;

    it("dit l'heure depuis le premier événement et une phrase par événement", () => {
        enFrancais(
            <JournalDesEvenements
                evenements={[
                    evt("rtf-node-transition", { node_name: "Accueil" }, "2026-11-04T10:00:00+00:00"),
                    evt("rtf-user-transcription", { text: "Bonjour", final: true }, "2026-11-04T10:00:04.2+00:00"),
                    evt("rtf-user-transcription", { text: "Bon", final: false }, "2026-11-04T10:00:04.3+00:00"),
                    evt("rtf-function-call-start", { function_name: "chercher_creneaux" }, "2026-11-04T10:01:31.4+00:00"),
                ]}
            />,
        );
        const lignes = screen.getAllByTestId("evenement-du-journal").map((l) => l.textContent);
        expect(lignes).toEqual([
            "00:00.0étape : Accueil",
            "00:04.2parole de l'appelant : « Bonjour »",
            "01:31.4outil chercher_creneaux : début",
        ]);
    });

    it("ne montre jamais le texte brut d'une erreur technique", () => {
        const phrase = phraseDeLEvenement(evt("rtf-pipeline-error", { error: "Traceback secret", processor: "STT" }, "2026-11-04T10:00:00+00:00"), t);
        expect(phrase).toBe("incident dans le circuit de l'appel (STT)");
        expect(phrase).not.toContain("secret");
    });

    it("un appel sans événement le dit", () => {
        enFrancais(<JournalDesEvenements evenements={[]} />);
        expect(screen.getByTestId("journal-vide")).toBeTruthy();
    });

    it("écrit les heures en minutes, secondes et dixièmes", () => {
        expect(heureDuJournal(0)).toBe("00:00.0");
        expect(heureDuJournal(151)).toBe("02:31.0");
        expect(heureDuJournal(11.84)).toBe("00:11.8");
    });
});

describe("le lecteur", () => {
    it("sans enregistrement : le lecteur est là, éteint, et le dit", () => {
        enFrancais(<LecteurConversation pisteAppelant={null} pisteAgent={null} enregistrement={null} ecrit={false} />);
        const lecteur = document.querySelector("[data-lecteur-conversation]") as HTMLElement;
        expect(lecteur.getAttribute("data-lecteur-conversation")).toBe("vide");
        expect(lecteur.textContent).toContain("Aucun enregistrement pour cet appel");
        expect((within(lecteur).getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    });

    it("une conversation écrite le dit autrement (jamais d'audio)", () => {
        enFrancais(<LecteurConversation pisteAppelant={null} pisteAgent={null} enregistrement={null} ecrit />);
        expect(document.body.textContent).toContain("Conversation écrite");
    });

    it("avec un seul enregistrement : le lecteur de cet enregistrement", () => {
        enFrancais(<LecteurConversation pisteAppelant={null} pisteAgent={null} enregistrement="r.wav" ecrit={false} />);
        expect(document.querySelector("[data-lecteur-conversation]")?.getAttribute("data-lecteur-conversation")).toBe("unique");
    });

    it("avec deux pistes : le lecteur à pistes, le choix de la piste dans la langue de l'écran", () => {
        enFrancais(<LecteurConversation pisteAppelant="u.wav" pisteAgent="b.wav" enregistrement="r.wav" ecrit={false} />);
        expect(screen.getByRole("button", { name: "Les deux pistes" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Écouter la piste de l'appelant seule" }).textContent).toBe("Appelant");
        expect(screen.getByRole("button", { name: "Écouter la piste de l'agent seule" }).textContent).toBe("Agent");
    });
});
