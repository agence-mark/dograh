/**
 * [.mark] Lot D (chantier fiabilite-fiche-et-renvoi): the two transfer buttons, as the
 * tester sees them.
 *
 * The questions this file answers:
 *
 *     When a transfer waits for the tester, do « Accepter le renvoi d'appel » and
 *     « Refuser le renvoi d'appel » appear, word for word, and does a click send the
 *     answer to the right run? Do they stay hidden (and silent) when nothing can be
 *     waiting? And do they appear where Evan tests: in the keyboard chat while a
 *     message is answered, and in the voice tester during a call?
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoutonsRenvoiEnTest } from "./BoutonsRenvoiEnTest";
import { FournisseurLangue } from "./langue/langue";

// The application opens in French (D12): the labels are read as Evan wrote them.
const enFrancais = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

const { lireEtat, decider, useWebSocketRTCMock, useTextChatSessionMock } = vi.hoisted(() => ({
    lireEtat: vi.fn(),
    decider: vi.fn(),
    useWebSocketRTCMock: vi.fn(),
    useTextChatSessionMock: vi.fn(),
}));

vi.mock("@/client", () => ({
    etatDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestGet: (...a: unknown[]) => lireEtat(...a),
    deciderDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestPost: (...a: unknown[]) => decider(...a),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock("@/app/workflow/[workflowId]/run/[runId]/hooks", () => ({ useWebSocketRTC: useWebSocketRTCMock }));
vi.mock("@/app/workflow/[workflowId]/run/[runId]/components", () => ({
    ApiKeyErrorDialog: () => null,
    ConnectionStatus: () => null,
    WorkflowConfigErrorDialog: () => null,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/app/workflow/[workflowId]/components/workflow-tester/useTextChatSession", () => ({
    useTextChatSession: useTextChatSessionMock,
}));

const ACCEPTER = "Accepter le renvoi d'appel";
const REFUSER = "Refuser le renvoi d'appel";

describe("Boutons du renvoi d'appel en test", () => {
    beforeEach(() => {
        lireEtat.mockReset();
        decider.mockReset();
    });

    it("affiche les deux boutons, libellés exacts, quand un renvoi attend", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: true } });
        enFrancais(<BoutonsRenvoiEnTest workflowId={7} runId={42} actif />);
        expect(await screen.findByRole("button", { name: ACCEPTER })).toBeTruthy();
        expect(screen.getByRole("button", { name: REFUSER })).toBeTruthy();
        expect(lireEtat).toHaveBeenCalledWith({ path: { workflow_id: 7, run_id: 42 } });
    });

    it("un clic sur Accepter envoie la décision au bon run", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: true } });
        decider.mockResolvedValue({ data: { en_attente: false } });
        enFrancais(<BoutonsRenvoiEnTest workflowId={7} runId={42} actif />);
        fireEvent.click(await screen.findByRole("button", { name: ACCEPTER }));
        await waitFor(() =>
            expect(decider).toHaveBeenCalledWith({ path: { workflow_id: 7, run_id: 42 }, body: { accepte: true } }),
        );
    });

    it("un clic sur Refuser envoie le refus", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: true } });
        decider.mockResolvedValue({ data: { en_attente: false } });
        enFrancais(<BoutonsRenvoiEnTest workflowId={7} runId={42} actif />);
        fireEvent.click(await screen.findByRole("button", { name: REFUSER }));
        await waitFor(() => expect(decider).toHaveBeenCalledWith(expect.objectContaining({ body: { accepte: false } })));
    });

    it("rien quand aucun renvoi n'attend", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: false } });
        enFrancais(<BoutonsRenvoiEnTest workflowId={7} runId={42} actif />);
        await waitFor(() => expect(lireEtat).toHaveBeenCalled());
        expect(screen.queryByRole("button", { name: ACCEPTER })).toBeNull();
    });

    it("inactif : ni bouton ni appel au serveur", () => {
        enFrancais(<BoutonsRenvoiEnTest workflowId={7} runId={42} actif={false} />);
        expect(lireEtat).not.toHaveBeenCalled();
        expect(screen.queryByRole("button", { name: ACCEPTER })).toBeNull();
    });

    it("au casque : les boutons apparaissent pendant l'appel", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: true } });
        useWebSocketRTCMock.mockReturnValue({
            audioRef: { current: null },
            connectionActive: true,
            permissionError: null,
            isCompleted: false,
            apiKeyModalOpen: false,
            setApiKeyModalOpen: vi.fn(),
            apiKeyError: null,
            apiKeyErrorCode: null,
            workflowConfigError: null,
            workflowConfigModalOpen: false,
            setWorkflowConfigModalOpen: vi.fn(),
            connectionStatus: "connected",
            start: vi.fn(),
            stop: vi.fn(),
            isStarting: false,
            feedbackMessages: [],
            appConfig: { backendStatus: "reachable" },
            appConfigLoading: false,
            refreshAppConfig: vi.fn(),
        });
        const { EmbeddedVoiceTester } = await import(
            "@/app/workflow/[workflowId]/components/workflow-tester/EmbeddedVoiceTester"
        );
        enFrancais(<EmbeddedVoiceTester workflowId={7} workflowRunId={42} accessToken="t" onReset={vi.fn()} />);
        expect(await screen.findByRole("button", { name: ACCEPTER })).toBeTruthy();
        expect(lireEtat).toHaveBeenCalledWith({ path: { workflow_id: 7, run_id: 42 } });
    });

    it("au clavier : les boutons apparaissent dans la conversation pendant la réponse", async () => {
        lireEtat.mockResolvedValue({ data: { en_attente: true } });
        useTextChatSessionMock.mockReturnValue({
            session: { workflow_run_id: 42, is_completed: false },
            started: true,
            draft: "",
            turns: [{ id: "t1", user_message: { text: "je voudrais parler à quelqu'un" } }],
            editingTurn: null,
            editingTurnId: null,
            creatingSession: false,
            sendingMessage: true,
            endingSession: false,
            activeTurnAction: null,
            composerId: "c",
            inputDisabled: true,
            conversationItems: [
                { kind: "message", id: "m1", role: "user", text: "je voudrais parler à quelqu'un", turnId: "t1" },
            ],
            setDraft: vi.fn(),
            startSession: vi.fn(),
            rewindTurn: vi.fn(),
            startEditingTurn: vi.fn(),
            cancelEditingTurn: vi.fn(),
            submitComposer: vi.fn(),
            endSession: vi.fn(),
        });
        // jsdom ne fait pas défiler : la conversation appelle scrollIntoView à chaque rendu.
        Element.prototype.scrollIntoView = vi.fn();
        const { ManualTextChatPanel } = await import(
            "@/app/workflow/[workflowId]/components/workflow-tester/ManualTextChatPanel"
        );
        enFrancais(<ManualTextChatPanel workflowId={7} ready disabled={false} disabledReason={null} />);
        expect(await screen.findByRole("button", { name: ACCEPTER })).toBeTruthy();
        expect(lireEtat).toHaveBeenCalledWith({ path: { workflow_id: 7, run_id: 42 } });
    });
});
