/**
 * [.mark] Call retention on screen (cloture-code-avant-migration, lot 6), rendered by the real theme.
 *
 * | Test | La garantie |
 * |---|---|
 * | defauts | la section est dans « Donnees du client » meme sans base rattachee ; chaque champ de l'inventaire y est trouve, avec les defauts de .mark (purge oui, 6 mois, audio non, 6 mois, essai a blanc oui) |
 * | passage | le dernier passage (essai a blanc ou reel, comptes, echecs) s'affiche ; sans passage, le dit |
 * | enregistrer | la charge utile est exactement ce qui est a l'ecran ; bouton ferme tant que rien ne change ou qu'une duree est hors bornes ; point orange du theme |
 * | plafond | l'installation qui interdit l'audio : l'interrupteur est ferme et dit pourquoi ; un refus du serveur est montre |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { INVENTAIRE_CONSERVATION_APPELS } from "./inventaire-organisation";
import { CHAMPS_CONSERVATION_APPELS } from "./SectionConservationAppels";
import { ThemeDonneesClient, useBaseClient } from "./ThemeDonneesClient";

const m = vi.hoisted(() => ({ base: vi.fn(), lire: vi.fn(), ecrire: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getBaseClientApiV1OrganizationsBaseClientGet: m.base,
    getConservationDesAppelsApiV1OrganizationsConservationAppelsGet: m.lire,
    putConservationDesAppelsApiV1OrganizationsConservationAppelsPut: m.ecrire,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

const SANS_BASE = { serveur_configure: true, nom_base: null, joignable: false, version: null, version_attendue: 3, refus: [], conservation: [] };
const DEFAUTS = { format: "conservation-appels-mark", version: 1, purge_activee: true, duree_mois: 6, audio_enregistre: false, audio_duree_mois: 6, essai_a_blanc: true };
const VUE = { reglages: DEFAUTS, audio_autorise_par_l_installation: true, dernier_passage: null };

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Donnees = ({ signaler = vi.fn() }: { signaler?: (id: string, modifie: boolean, enErreur: boolean) => void }) => {
    const base = useBaseClient();
    return <ThemeDonneesClient ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={signaler} base={base} />;
};

const rendre = (noeud: ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

const section = async () => {
    const champ = await waitFor(() => {
        const c = document.querySelector('[data-reglage="duree_mois"]');
        expect(c).not.toBeNull();
        return c as HTMLElement;
    });
    return champ.closest("[data-intertitre], section, div[id^='donnees-conservation-appels']") ?? champ.parentElement!;
};

describe("Call retention (« Client data »)", () => {
    it("is drawn even with no client database attached, with .mark's defaults, every inventory field found", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.lire.mockResolvedValue({ data: VUE });
        rendre(<Donnees />);
        await section();
        for (const cle of CHAMPS_CONSERVATION_APPELS) {
            expect(document.querySelector(`[data-reglage="${cle}"]`), `${cle} is on screen`).not.toBeNull();
        }
        // Displayed in the inventory = drawn; no more, no less.
        expect(Object.entries(INVENTAIRE_CONSERVATION_APPELS).filter(([, e]) => "champ" in e).map(([k]) => k).sort()).toEqual(
            [...CHAMPS_CONSERVATION_APPELS].sort(),
        );
        expect((document.getElementById("conservation-appels-purge") as HTMLElement).getAttribute("data-state")).toBe("checked");
        expect((document.getElementById("conservation-appels-duree") as HTMLInputElement).value).toBe("6");
        expect((document.getElementById("conservation-appels-audio") as HTMLElement).getAttribute("data-state")).toBe("unchecked");
        expect((document.getElementById("conservation-appels-audio-duree") as HTMLInputElement).value).toBe("6");
        expect((document.getElementById("conservation-appels-blanc") as HTMLElement).getAttribute("data-state")).toBe("checked");
        expect(screen.getByTestId("aucun-passage-conservation")).toBeTruthy();
    });

    it("shows the last passage: dry run or real, the counts and what is left for tomorrow", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.lire.mockResolvedValue({
            data: {
                ...VUE,
                dernier_passage: {
                    passe_le: "2026-10-23T01:43:00Z", a_blanc: true, runs_texte: 41, runs_audio: 12, objets: 77, echecs: 2, incomplet: false,
                    duree_mois: 6, audio_duree_mois: 6,
                },
            },
        });
        rendre(<Donnees />);
        await section();
        const texte = (await screen.findByTestId("dernier-passage-conservation")).textContent ?? "";
        expect(texte).toMatch(/dry run|essai à blanc/);
        expect(texte).toContain("41");
        expect(texte).toContain("12");
        expect(texte).toContain("77");
        expect(texte).toMatch(/2 (left for tomorrow|repris demain)/);
    });

    it("saves exactly what is on screen, and the button stays shut until something changes or when a duration is out of bounds", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.lire.mockResolvedValue({ data: VUE });
        m.ecrire.mockImplementation(async ({ body }: { body: typeof DEFAUTS }) => ({ data: { ...VUE, reglages: body } }));
        const signaler = vi.fn();
        rendre(<Donnees signaler={signaler} />);
        await section();
        const bouton = screen.getByTestId("enregistrer-conservation-appels") as HTMLButtonElement;
        expect(bouton.disabled, "nothing changed").toBe(true);

        const duree = document.getElementById("conservation-appels-duree") as HTMLInputElement;
        fireEvent.change(duree, { target: { value: "0" } });
        expect(bouton.disabled, "0 months is out of bounds").toBe(true);
        fireEvent.change(duree, { target: { value: "121" } });
        expect(bouton.disabled, "121 months is out of bounds").toBe(true);
        fireEvent.change(duree, { target: { value: "9" } });
        fireEvent.click(document.getElementById("conservation-appels-blanc") as HTMLElement);
        expect(bouton.disabled).toBe(false);
        await waitFor(() => expect(signaler).toHaveBeenCalledWith("donnees", true, false));

        fireEvent.click(bouton);
        await waitFor(() => expect(m.ecrire).toHaveBeenCalledTimes(1));
        expect(m.ecrire.mock.calls[0][0].body).toEqual({ ...DEFAUTS, duree_mois: 9, essai_a_blanc: false });
        await waitFor(() => expect((screen.getByTestId("enregistrer-conservation-appels") as HTMLButtonElement).disabled).toBe(true));
    });

    it("locks the audio switch, and says why, when the installation forbids the audio", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.lire.mockResolvedValue({ data: { ...VUE, audio_autorise_par_l_installation: false } });
        rendre(<Donnees />);
        const champ = await section();
        const audio = document.getElementById("conservation-appels-audio") as HTMLElement;
        expect(audio.hasAttribute("disabled")).toBe(true);
        expect(within(document.body).getByText(/ENABLE_CALL_RECORDING_UPLOAD/)).toBeTruthy();
        expect(champ).toBeTruthy();
    });

    it("shows the server's refusal", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.lire.mockResolvedValue({ data: VUE });
        m.ecrire.mockResolvedValue({ error: { detail: [{ msg: "The installation forbids recording the audio", loc: ["body", "audio_enregistre"] }] } });
        rendre(<Donnees />);
        await section();
        fireEvent.click(document.getElementById("conservation-appels-audio") as HTMLElement);
        fireEvent.click(screen.getByTestId("enregistrer-conservation-appels"));
        expect((await screen.findByTestId("erreur-conservation-appels")).textContent).toContain("forbids recording the audio");
    });
});
