/**
 * [.mark] Les essais d'un outil HTTP à l'écran (correctifs-apres-banc-v4, lot 5, plan 5.1).
 *
 * | Test | La garantie |
 * |---|---|
 * | lecture et charge | les trois clés se lisent avec leurs défauts et ne s'écrivent que si elles ne sont pas au défaut |
 * | délai total | l'aperçu calcule comme `delai_total_s` du serveur (délai × (1 + essais) + attentes) |
 * | bornes | 0 à 2 essais et 30 s d'attente, comme `api/schemas/tool.py` |
 * | écran | le bloc montre les quatre cas du tableau 5.1 et l'aperçu délai × essais |
 * | aller-retour | la vraie page de l'outil : ouverte sur un outil à 2 essais, elle ne perd aucune clé à l'enregistrement et envoie les essais choisis |
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ATTENTE_MAX_S,casRelances, chargeEssais, delaiTotalS, ESSAIS_MAX, ESSAIS_PAR_DEFAUT, type EssaisOutil, lireEssais } from "./essais-outil";
import { EssaisOutilHttp } from "./EssaisOutilHttp";

vi.mock("@/components/ui/select", () => import("../reglages-agent/references/select-natif"));

const m = vi.hoisted(() => ({
    outil: null as unknown,
    update: vi.fn(),
}));
vi.mock("next/navigation", () => ({
    useParams: () => ({ toolUuid: "outil-1" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
const auth = vi.hoisted(() => ({ user: { id: "u-1" }, loading: false, getAccessToken: async () => "jeton", redirectToLogin: () => undefined }));
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getToolApiV1ToolsToolUuidGet: () => Promise.resolve({ data: m.outil, error: undefined }),
    updateToolApiV1ToolsToolUuidPut: (options: unknown) => {
        m.update(options);
        return Promise.resolve({ data: m.outil, error: undefined });
    },
    getWorkflowsSummaryApiV1WorkflowSummaryGet: () => Promise.resolve({ data: [], error: undefined }),
    listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] }, error: undefined }),
}));

afterEach(() => {
    cleanup();
    m.update.mockReset();
});

describe("[.mark] essais d'un outil : le calcul", () => {
    it("reads the three keys with the defaults of the server and writes only what is not a default", () => {
        expect(lireEssais({})).toEqual(ESSAIS_PAR_DEFAUT);
        expect(lireEssais(null)).toEqual(ESSAIS_PAR_DEFAUT);
        expect(lireEssais({ essais: 9, attente_entre_essais_s: 99 })).toMatchObject({ essais: ESSAIS_MAX, attente_entre_essais_s: ATTENTE_MAX_S });
        expect(lireEssais({ essais: "x", attente_entre_essais_s: "y", sans_risque_de_doublon: "oui" })).toEqual(ESSAIS_PAR_DEFAUT);
        expect(chargeEssais(ESSAIS_PAR_DEFAUT)).toEqual({});
        expect(chargeEssais({ essais: 2, attente_entre_essais_s: 1, sans_risque_de_doublon: false })).toEqual({ essais: 2 });
        const tout: EssaisOutil = { essais: 1, attente_entre_essais_s: 2.5, sans_risque_de_doublon: true };
        expect(chargeEssais(tout)).toEqual({ essais: 1, attente_entre_essais_s: 2.5, sans_risque_de_doublon: true });
        // Une lecture puis une charge rend les mêmes clés.
        expect(chargeEssais(lireEssais({ essais: 1, attente_entre_essais_s: 2.5, sans_risque_de_doublon: true }))).toEqual(tout);
    });

    it("computes the total delay like the server does", () => {
        // delai_total_s : (1 + essais) délais et les attentes entre eux.
        expect(delaiTotalS(5000, ESSAIS_PAR_DEFAUT)).toBe(5);
        expect(delaiTotalS(5000, { essais: 2, attente_entre_essais_s: 1, sans_risque_de_doublon: false })).toBe(17);
        expect(delaiTotalS(4000, { essais: 1, attente_entre_essais_s: 0.5, sans_risque_de_doublon: true })).toBe(8.5);
        const python = readFileSync(join(process.cwd(), "..", "api/services/workflow/tools/custom_tool.py"), "utf8");
        expect(python).toContain("return delai_s * (1 + essais) + attente * essais");
    });

    it("holds the bounds of the server schema", () => {
        const schema = readFileSync(join(process.cwd(), "..", "api/schemas/tool.py"), "utf8");
        expect(schema).toMatch(/essais: int = Field\(\s*default=0,\s*ge=0,\s*le=2,/);
        expect(schema).toMatch(/attente_entre_essais_s: float = Field\(\s*default=1\.0,\s*ge=0,\s*le=30,/);
        expect(ESSAIS_MAX).toBe(2);
        expect(ATTENTE_MAX_S).toBe(30);
    });

    it("tells which of the four cases are called again (table 5.1)", () => {
        expect(casRelances(ESSAIS_PAR_DEFAUT)).toEqual({ pasPartie: false, delai: false, erreur5xx: false, refus4xx: false });
        expect(casRelances({ essais: 1, attente_entre_essais_s: 1, sans_risque_de_doublon: false })).toEqual({ pasPartie: true, delai: false, erreur5xx: false, refus4xx: false });
        expect(casRelances({ essais: 1, attente_entre_essais_s: 1, sans_risque_de_doublon: true })).toEqual({ pasPartie: true, delai: true, erreur5xx: true, refus4xx: false });
    });
});

const Bloc = ({ depart }: { depart: EssaisOutil }) => {
    const [valeur, setValeur] = useState(depart);
    return <EssaisOutilHttp valeur={valeur} onChange={setValeur} timeoutMs={5000} />;
};

describe("[.mark] essais d'un outil : le bloc", () => {
    it("shows the preview delay × tries and the four cases, and follows the choices", () => {
        render(<Bloc depart={ESSAIS_PAR_DEFAUT} />);
        expect(document.getElementById("outil_attente_entre_essais")).toBeNull();
        expect(document.querySelector('[data-ligne="delai-total"]')?.textContent).toContain("A single request, 5 s at most");
        fireEvent.change(document.getElementById("outil_essais") as HTMLSelectElement, { target: { value: "2" } });
        expect(document.querySelector('[data-ligne="delai-total"]')?.textContent).toContain("5 s × 3 requests + 1 s × 2 wait(s) = 17 s at most.");
        fireEvent.change(document.getElementById("outil_attente_entre_essais") as HTMLInputElement, { target: { value: "3" } });
        expect(document.querySelector('[data-ligne="delai-total"]')?.textContent).toContain("= 21 s at most.");
        const cas = (c: string) => document.querySelector(`[data-cas="${c}"]`)?.textContent ?? "";
        expect(cas("pasPartie")).toContain("yes");
        expect(cas("delai")).toContain("no");
        expect(cas("refus4xx")).toContain("never");
        fireEvent.click(document.getElementById("outil_sans_risque_de_doublon") as HTMLElement);
        expect(cas("delai")).toContain("yes");
        expect(cas("erreur5xx")).toContain("yes");
        expect(cas("refus4xx")).toContain("never");
    });
});

const OUTIL = {
    id: 1,
    tool_uuid: "outil-1",
    name: "chercher_dates",
    description: "Cherche des dates.",
    category: "http_api",
    status: "active",
    definition: {
        schema_version: 1,
        type: "http_api",
        config: {
            method: "POST",
            url: "https://exemple.test/dates",
            timeout_ms: 7000,
            essais: 2,
            attente_entre_essais_s: 2.5,
            sans_risque_de_doublon: true,
            body_format: "json",
        },
    },
};

describe("[.mark] essais d'un outil : la vraie page", () => {
    it("opens a tool with its tries, keeps them on save, and sends the ones chosen", async () => {
        m.outil = OUTIL;
        const { default: PageOutil } = await import("@/app/tools/[toolUuid]/page");
        render(<PageOutil />);
        await waitFor(() => expect(document.getElementById("outil_essais")).not.toBeNull());
        const selecteur = document.getElementById("outil_essais") as HTMLSelectElement;
        expect(selecteur.value).toBe("2");
        expect((document.getElementById("outil_attente_entre_essais") as HTMLInputElement).value).toBe("2.5");
        expect(document.getElementById("outil_sans_risque_de_doublon")?.getAttribute("aria-checked")).toBe("true");
        // 7 s × 3 + 2,5 s × 2 = 26 s au plus.
        expect(document.querySelector('[data-ligne="delai-total"]')?.textContent).toContain("= 26 s at most");

        // Enregistrer sans toucher aux essais : les trois clés repartent telles quelles.
        fireEvent.click(await screen.findByRole("button", { name: /save/i }));
        await waitFor(() => expect(m.update).toHaveBeenCalledTimes(1));
        const config = m.update.mock.calls[0][0].body.definition.config;
        expect(config).toMatchObject({ timeout_ms: 7000, essais: 2, attente_entre_essais_s: 2.5, sans_risque_de_doublon: true });

        // Les essais choisis partent ; un essai à 0 n'écrit plus rien (le défaut est le comportement d'avant).
        m.update.mockClear();
        fireEvent.change(selecteur, { target: { value: "0" } });
        fireEvent.click(document.getElementById("outil_sans_risque_de_doublon") as HTMLElement);
        fireEvent.click(await screen.findByRole("button", { name: /save/i }));
        await waitFor(() => expect(m.update).toHaveBeenCalledTimes(1));
        const apres = m.update.mock.calls[0][0].body.definition.config;
        expect(apres.essais).toBeUndefined();
        expect(apres.attente_entre_essais_s).toBeUndefined();
        expect(apres.sans_risque_de_doublon).toBeUndefined();
        expect(apres.timeout_ms).toBe(7000);
    }, 30000);
});
