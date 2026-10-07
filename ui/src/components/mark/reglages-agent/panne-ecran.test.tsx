/**
 * [.mark] The outage fallback on screen (chantier l-agent-travaille, L7), rendered.
 *
 *   - the agent's switch: off by default, its three thresholds shown only when on, bounds said
 *     before the server refuses them;
 *   - the organization's block: the emergency address saved as typed, the text of the Bin shown,
 *     the catch-up asked at once and its result said;
 *   - the catalogue of sentences offers the three outage sentences once.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { BlocSecoursPanne } from "../parametres-organisation/BlocSecoursPanne";
import { PHRASES_DE_PANNE } from "../parametres-organisation/ModalePhrases";
import { erreursPanne, lirePanne, PANNE_ETEINTE, SectionPanneAgent } from "./SectionPanneAgent";

const m = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), rattrapage: vi.fn(), secours: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    getPanneApiV1OrganizationsPanneGet: m.get,
    putPanneApiV1OrganizationsPannePut: m.put,
    postRattrapageApiV1OrganizationsPanneRattrapagePost: m.rattrapage,
    postAdresseDeSecoursApiV1OrganizationsPanneAdresseDeSecoursPost: m.secours,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Section = ({ recu }: { recu: (v: unknown) => void }) => {
    const [valeur, setValeur] = useState(lirePanne(null));
    return (
        <FournisseurLangue>
            <SectionPanneAgent
                valeur={valeur}
                onChange={(v) => {
                    setValeur(v);
                    recu(v);
                }}
            />
        </FournisseurLangue>
    );
};

describe("[.mark] the outage fallback on screen", () => {
    it("is off by default and shows its thresholds once on", () => {
        const recu = vi.fn();
        render(<Section recu={recu} />);
        expect(document.getElementById("panne_delai_modele_s")).toBeNull();
        fireEvent.click(screen.getByRole("switch", { name: /Passer l'appel/ }));
        expect(document.getElementById("panne_delai_modele_s")).not.toBeNull();
        fireEvent.change(document.getElementById("panne_sonnerie_s")!, { target: { value: "30" } });
        expect(recu.mock.calls.at(-1)?.[0]).toEqual({ actif: true, delai_modele_s: 4, delai_voix_s: 3, sonnerie_s: 30 });
        expect(erreursPanne({ ...PANNE_ETEINTE, actif: true, delai_voix_s: 0.1 })).toHaveLength(1);
        expect(erreursPanne({ ...PANNE_ETEINTE, delai_voix_s: 0.1 })).toEqual([]);
    });

    it("saves the two emergency addresses, shows the two Bins and catches up at once", async () => {
        const textes = { texte_du_bin: "<Response>{{Renvoi}}</Response>", texte_du_bin_promesse: "<Response><Hangup/></Response>" };
        m.get.mockResolvedValue({ data: { reglages: { format: "panne-mark", version: 1, url_secours: null, url_secours_promesse: null }, ...textes } });
        m.put.mockImplementation(({ body }) => Promise.resolve({ data: { reglages: body, ...textes } }));
        m.rattrapage.mockResolvedValue({ data: { appels_lus: 4, demandes_creees: 2, deja_connus: 0, erreurs: [] } });
        render(
            <FournisseurLangue>
                <BlocSecoursPanne />
            </FournisseurLangue>,
        );
        await screen.findAllByPlaceholderText("https://handler.twilio.com/twiml/EH…");
        expect((document.getElementById("panne-texte-bin") as HTMLTextAreaElement).value).toContain("{{Renvoi}}");
        expect((document.getElementById("panne-texte-bin-promesse") as HTMLTextAreaElement).value).toContain("<Hangup/>");
        fireEvent.change(document.getElementById("panne-url-secours") as HTMLInputElement, { target: { value: " https://handler.twilio.com/twiml/EHessai " } });
        fireEvent.change(document.getElementById("panne-url-secours-promesse") as HTMLInputElement, { target: { value: "https://handler.twilio.com/twiml/EHpromesse" } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer l'adresse/ }));
        await waitFor(() =>
            expect(m.put).toHaveBeenCalledWith({
                body: { format: "panne-mark", version: 1, url_secours: "https://handler.twilio.com/twiml/EHessai", url_secours_promesse: "https://handler.twilio.com/twiml/EHpromesse" },
            }),
        );
        fireEvent.click(screen.getByRole("button", { name: /Rattraper les appels perdus/ }));
        expect(await screen.findByText(/2 demande\(s\) à rappeler créée\(s\)/)).toBeTruthy();
        expect(m.secours).not.toHaveBeenCalled(); // writing at Twilio is never automatic
    });

    it("offers the three outage sentences of the catalogue", () => {
        expect(PHRASES_DE_PANNE.map((p) => p.variable)).toEqual(["phrase_renvoi_panne", "phrase_rappel_panne", "phrase_excuse_panne"]);
        expect(PHRASES_DE_PANNE.every((p) => (p.contenu ?? "").length > 10)).toBe(true);
    });
});
