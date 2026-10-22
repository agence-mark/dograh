/**
 * [.mark] Value list boxes on screen (cloture-code-avant-migration, lot F3), rendered by the real theme.
 *
 * | Test | La garantie |
 * |---|---|
 * | rendu | la section est dans « Donnees du client » quand une base est joignable ; une ligne par valeur, la case que le serveur dit pour sa liste, rien d'autre |
 * | sans base | pas de base rattachee : la section n'existe pas et rien n'est lu |
 * | enregistrer | seules les cases changees partent ; bouton ferme tant que rien ne change ; point orange du theme |
 * | refus | le refus du serveur est montre |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { CASES_LISTES_VALEURS } from "./SectionListesValeurs";
import { ThemeDonneesClient, useBaseClient } from "./ThemeDonneesClient";

const m = vi.hoisted(() => ({ base: vi.fn(), lire: vi.fn(), ecrire: vi.fn(), conservation: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getBaseClientApiV1OrganizationsBaseClientGet: m.base,
    getConservationDesAppelsApiV1OrganizationsConservationAppelsGet: m.conservation,
    getListesValeursApiV1OrganizationsListesValeursGet: m.lire,
    putListesValeursApiV1OrganizationsListesValeursPut: m.ecrire,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

const SANS_BASE = { serveur_configure: true, nom_base: null, joignable: false, version: null, version_attendue: 17, refus: [], conservation: [] };
const AVEC_BASE = { serveur_configure: true, nom_base: "client_a", joignable: true, version: 17, version_attendue: 17, refus: [], conservation: [] };
const CONSERVATION = { data: { reglages: { purge_activee: true, duree_mois: 6, audio_enregistre: false, audio_duree_mois: 6, essai_a_blanc: true }, audio_autorise_par_l_installation: true, dernier_passage: null } };
const valeur = (code: string, libelle: string, cases: Record<string, boolean> = {}) => ({ code, libelle, ordre: 1, actif: true, regle_seul: false, opportunite: false, urgent: false, ...cases });
const VUE = {
    listes: [
        { liste: "issue_appel", cases: ["regle_seul"], valeurs: [valeur("autre", "Autre"), valeur("regle", "Réglé", { regle_seul: true })] },
        { liste: "motif_appel", cases: ["opportunite"], valeurs: [valeur("devis", "Devis")] },
        { liste: "degre_urgence", cases: ["urgent"], valeurs: [] },
    ],
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Donnees = ({ signaler = vi.fn() }: { signaler?: (id: string, modifie: boolean, enErreur: boolean) => void }) => {
    const base = useBaseClient();
    return <ThemeDonneesClient ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={signaler} base={base} />;
};
const rendre = (noeud: ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

describe("Value list boxes (« Client data »)", () => {
    it("draws one row per value with the box the server names for its list, and an empty list says so", async () => {
        m.base.mockResolvedValue({ data: AVEC_BASE });
        m.conservation.mockResolvedValue(CONSERVATION);
        m.lire.mockResolvedValue({ data: VUE });
        rendre(<Donnees />);
        await screen.findByTestId("enregistrer-listes-valeurs");
        expect(document.querySelectorAll("[data-valeur]").length).toBe(3);
        const boites = [...document.querySelectorAll("[data-reglage]")].map((e) => e.getAttribute("data-reglage"));
        expect(boites.filter((b) => (CASES_LISTES_VALEURS as readonly string[]).includes(b ?? "")).sort()).toEqual(["opportunite", "regle_seul", "regle_seul"]);
        expect(document.getElementById("liste-issue_appel-regle-regle_seul")!.getAttribute("data-state")).toBe("checked");
        expect(document.getElementById("liste-issue_appel-autre-regle_seul")!.getAttribute("data-state")).toBe("unchecked");
        expect(screen.getByTestId("liste-vide-degre_urgence")).toBeTruthy();
    });

    it("does not exist, and reads nothing, with no database attached", async () => {
        m.base.mockResolvedValue({ data: SANS_BASE });
        m.conservation.mockResolvedValue(CONSERVATION);
        rendre(<Donnees />);
        await waitFor(() => expect(m.conservation).toHaveBeenCalled());
        expect(screen.queryByTestId("enregistrer-listes-valeurs")).toBeNull();
        expect(m.lire).not.toHaveBeenCalled();
    });

    it("sends only the boxes that changed, and the button stays shut until something changes", async () => {
        m.base.mockResolvedValue({ data: AVEC_BASE });
        m.conservation.mockResolvedValue(CONSERVATION);
        m.lire.mockResolvedValue({ data: VUE });
        m.ecrire.mockResolvedValue({
            data: { listes: [{ ...VUE.listes[0], valeurs: [valeur("autre", "Autre", { regle_seul: true }), VUE.listes[0].valeurs[1]] }, VUE.listes[1], VUE.listes[2]] },
        });
        const signaler = vi.fn();
        rendre(<Donnees signaler={signaler} />);
        const bouton = (await screen.findByTestId("enregistrer-listes-valeurs")) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.click(document.getElementById("liste-issue_appel-autre-regle_seul") as HTMLElement);
        expect(bouton.disabled).toBe(false);
        await waitFor(() => expect(signaler).toHaveBeenCalledWith("donnees", true, false));
        fireEvent.click(bouton);
        await waitFor(() => expect(m.ecrire).toHaveBeenCalledTimes(1));
        expect(m.ecrire.mock.calls[0][0].body).toEqual({ valeurs: [{ liste: "issue_appel", code: "autre", regle_seul: true }] });
        await waitFor(() => expect((screen.getByTestId("enregistrer-listes-valeurs") as HTMLButtonElement).disabled).toBe(true));
    });

    it("shows the server's refusal", async () => {
        m.base.mockResolvedValue({ data: AVEC_BASE });
        m.conservation.mockResolvedValue(CONSERVATION);
        m.lire.mockResolvedValue({ data: VUE });
        m.ecrire.mockResolvedValue({ error: { detail: "« x » is not a value of the list « issue_appel »." } });
        rendre(<Donnees />);
        await screen.findByTestId("enregistrer-listes-valeurs");
        fireEvent.click(document.getElementById("liste-motif_appel-devis-opportunite") as HTMLElement);
        fireEvent.click(screen.getByTestId("enregistrer-listes-valeurs"));
        expect((await screen.findByTestId("erreur-listes-valeurs")).textContent).toContain("is not a value of the list");
    });
});
