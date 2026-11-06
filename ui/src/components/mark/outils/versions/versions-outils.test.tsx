/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : les versions des outils à l'écran.
 *
 * Questions de ce fichier :
 *
 *     L'onglet « Versions » dit-il qui utilise quelle version et combien d'agents restent en arrière ?
 *     « Passer à la v5 » demande-t-il confirmation, puis écrit-il dans la bonne branche (celle de la ligne) et le dit-il ?
 *     L'étape montre-t-elle la version et la ligne « une v5 existe » seulement quand un outil est en retard ?
 *     La ligne conseillée « Les outils sont à jour » de « Prêt à publier » nomme-t-elle les outils en retard ?
 *     Les textes sont-ils dits en français et en anglais ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListePret, type LigneDePret } from "../../agent/pret/ListePret";
import { TITRES_DES_LIGNES } from "../../agent/pret/textes";
import { FournisseurLangue } from "../../langue/langue";
import { OngletVersions } from "./OngletVersions";
import { REGLE_VERSIONS_OUTIL, T } from "./textes";
import { VersionsDansEtape } from "./VersionsDansEtape";

const m = vi.hoisted(() => ({ versions: vi.fn(), agent: vi.fn(), passer: vi.fn(), workflowId: 7 as number | undefined }));

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    lireLesVersionsDUnOutilApiV1BuilderOutilsToolUuidVersionsGet: (o: unknown) => m.versions(o),
    lireLesOutilsDeLAgentApiV1BuilderOutilsAgentWorkflowIdGet: (o: unknown) => m.agent(o),
    passerAUneVersionApiV1BuilderOutilsAgentWorkflowIdVersionPut: (o: unknown) => m.passer(o),
}));
vi.mock("@/app/workflow/[workflowId]/contexts/WorkflowContext", () => ({ useWorkflowOptional: () => ({ workflowId: m.workflowId }) }));

afterEach(() => cleanup());
beforeEach(() => {
    m.versions.mockReset();
    m.agent.mockReset();
    m.passer.mockReset();
    m.workflowId = 7;
    m.passer.mockResolvedValue({ data: { ok: true } });
});

const VUE = {
    tool_uuid: "u-reserver",
    nom: "reserver",
    courante: 5,
    agents_en_retard: 2,
    versions: [
        { version: 5, nom: "reserver", cree_le: "2026-11-04T15:40:00Z", courante: true },
        { version: 4, nom: "reserver", cree_le: "2026-10-28T10:15:00Z", courante: false },
    ],
    usage: [
        { workflow_id: 7, agent: "Standard Durand", branche: "Principale", branche_id: null, version_agent: 3, version_outil: 4, en_ligne: true, brouillon: false },
        { workflow_id: 7, agent: "Standard Durand", branche: "Accueil court", branche_id: 12, version_agent: 1, version_outil: 4, en_ligne: true, brouillon: false },
        { workflow_id: 9, agent: "Prise de RDV", branche: "Principale", branche_id: null, version_agent: 2, version_outil: 5, en_ligne: true, brouillon: false },
    ],
};

const monter = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("l'onglet Versions d'un outil", () => {
    it("dit qui utilise quelle version, combien d'agents restent en arrière, et la règle en bulle", async () => {
        m.versions.mockResolvedValue({ data: VUE });
        monter(<OngletVersions toolUuid="u-reserver" nom="reserver" />);
        await screen.findByText("2 agents restent sur la version précédente");
        expect(screen.getByText(/v5 · dernière/i)).toBeTruthy();
        expect(screen.getByText("Prise de RDV")).toBeTruthy();
        expect(screen.getAllByText("Standard Durand")).toHaveLength(2);
        // « Passer à la v5 » seulement sur les agents restés en v4, jamais sur la dernière version
        expect(screen.getAllByRole("button", { name: "Passer à la v5" })).toHaveLength(2);
        expect(m.versions.mock.calls[0][0]).toEqual({ path: { tool_uuid: "u-reserver" } });
    });

    it("demande confirmation, puis écrit dans la branche de la ligne (pas dans l'éditeur) et le dit", async () => {
        m.versions.mockResolvedValue({ data: VUE });
        monter(<OngletVersions toolUuid="u-reserver" nom="reserver" />);
        await screen.findByText("2 agents restent sur la version précédente");
        fireEvent.click(screen.getAllByRole("button", { name: "Passer à la v5" })[1]);
        // rien n'est écrit avant la confirmation
        expect(m.passer).not.toHaveBeenCalled();
        expect(await screen.findByText(/pour « Standard Durand », branche Accueil court/)).toBeTruthy();
        expect(screen.getByText(/rien n'est publié, les appels en cours gardent la v4/)).toBeTruthy();
        fireEvent.click(document.querySelector("[data-confirmer-passage]") as HTMLElement);
        await waitFor(() => expect(m.passer).toHaveBeenCalledTimes(1));
        expect(m.passer.mock.calls[0][0]).toEqual({
            path: { workflow_id: 7 },
            body: { tool_uuid: "u-reserver", version: 5, suivre_l_en_tete: false, branche_id: 12 },
        });
        // la liste est relue après le passage
        await waitFor(() => expect(m.versions.mock.calls.length).toBeGreaterThan(1));
    });

    it("n'écrit rien quand on annule, et dit l'échec sans le texte du serveur", async () => {
        m.versions.mockResolvedValue({ data: VUE });
        monter(<OngletVersions toolUuid="u-reserver" nom="reserver" />);
        await screen.findByText("2 agents restent sur la version précédente");
        fireEvent.click(screen.getAllByRole("button", { name: "Passer à la v5" })[0]);
        fireEvent.click(await screen.findByRole("button", { name: "Annuler" }));
        expect(m.passer).not.toHaveBeenCalled();
        m.passer.mockResolvedValue({ error: { detail: "Traceback interne SQL" } });
        fireEvent.click(screen.getAllByRole("button", { name: "Passer à la v5" })[0]);
        fireEvent.click(document.querySelector("[data-confirmer-passage]") as HTMLElement);
        await waitFor(() => expect(m.passer).toHaveBeenCalledTimes(1));
        expect(document.body.textContent).not.toContain("Traceback interne SQL");
    });

    it("dit une panne de lecture, sans écran blanc", async () => {
        m.versions.mockResolvedValue({ error: { detail: "boum" } });
        monter(<OngletVersions toolUuid="u-reserver" nom="reserver" />);
        expect(await screen.findByText("Les versions n'ont pas pu être lues. Réessayez.")).toBeTruthy();
    });
});

describe("l'étape", () => {
    const OUTILS = {
        data: {
            source: "brouillon",
            outils: [
                { tool_uuid: "u-reserver", nom: "reserver", epinglee: 4, courante: 5, figee: true },
                { tool_uuid: "u-chercher", nom: "chercher", epinglee: 3, courante: 3, figee: true },
            ],
        },
    };

    it("montre « une v5 existe » et le bouton pour un outil en retard seulement, et écrit dans la branche ouverte", async () => {
        m.agent.mockResolvedValue(OUTILS);
        monter(<VersionsDansEtape outilsDeLEtape={["u-reserver", "u-chercher"]} />);
        await screen.findByText(/une v5 existe/);
        expect(screen.queryByText(/chercher v3/)).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Passer à la v5" }));
        fireEvent.click(await screen.findByText("Passer à la v5", { selector: "[data-confirmer-passage]" }));
        await waitFor(() => expect(m.passer).toHaveBeenCalledTimes(1));
        expect(m.passer.mock.calls[0][0].body).toEqual({ tool_uuid: "u-reserver", version: 5, suivre_l_en_tete: true, branche_id: null });
    });

    it("ne montre rien quand tout est à jour ou quand l'étape n'a pas l'outil en retard", async () => {
        m.agent.mockResolvedValue(OUTILS);
        const { container } = monter(<VersionsDansEtape outilsDeLEtape={["u-chercher"]} />);
        await waitFor(() => expect(m.agent).toHaveBeenCalled());
        expect(container.querySelector("[data-versions-etape]")).toBeNull();
    });
});

describe("Prêt à publier et les textes", () => {
    it("la ligne conseillée « Les outils sont à jour » nomme les outils en retard et mène à l'étape", () => {
        const regler = vi.fn();
        const ligne = {
            id: "outils_a_jour",
            niveau: "conseille",
            etat: "a_faire",
            theme: "agent",
            source: "outils_a_jour",
            manquants: ["u-reserver"],
            noms: ["reserver"],
            noeud_id: "1",
            corrections: [],
        } as unknown as LigneDePret;
        monter(<ListePret lignes={[ligne]} textesDesEtapes={{}} regler={regler} />);
        expect(screen.getByText("Les outils sont à jour")).toBeTruthy();
        expect(screen.getByText("reserver")).toBeTruthy(); // le nom, jamais l'identifiant
        expect(document.body.textContent).not.toContain("u-reserver");
        expect(screen.getByText("conseillé")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Régler" }));
        expect(regler.mock.calls[0][0].noeud_id).toBe("1");
    });

    it("tous les textes existent en français et en anglais, et la règle n'est dite qu'une fois", () => {
        const textes = [
            REGLE_VERSIONS_OUTIL,
            T.description,
            T.annuler,
            T.echec,
            T.dansLeBrouillon,
            T.derniere,
            T.outilsAJourTitre,
            T.outilsAJourSource,
            T.passerA(5),
            T.retard(1),
            T.retard(3),
            T.corps("x", 4, 5, "A", "B"),
            T.corps("x", 4, 5, "", ""),
            T.ecrite("x", 5, "A", "B"),
            T.ecrite("x", 5, "", ""),
            T.uneExiste(5),
        ];
        for (const texte of textes) {
            expect(texte.fr.length).toBeGreaterThan(3);
            expect(texte.en.length).toBeGreaterThan(3);
            expect(texte.en).not.toBe(texte.fr);
        }
        expect(TITRES_DES_LIGNES.outils_a_jour.titre.fr).toBe("Les outils sont à jour");
    });
});
