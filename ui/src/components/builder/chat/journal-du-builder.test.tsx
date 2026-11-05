/**
 * [.mark] Partie 3, N1 (sous-lot 4) : « Annuler » sur la ligne d'action et le journal du builder.
 * Le serveur décide ce qui se défait ; l'écran le lit dans le résultat et le dit, sans jamais deviner.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ annuler: vi.fn(), lire: vi.fn(), succes: vi.fn(), echec: vi.fn() }));

vi.mock("@/client", () => ({
    annulerUneActionDuBuilderApiV1BuilderJournalLigneIdAnnulerPost: (o: unknown) => m.annuler(o),
    lireLeJournalDuBuilderApiV1BuilderJournalGet: (o: unknown) => m.lire(o),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: { succes: m.succes, echec: m.echec } }));

import { LigneAction } from "./cartes";
import { appliquer, type LigneDuFil } from "./evenements";
import { JournalDuBuilder } from "./journal-du-builder";

afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const ligne = (journal: unknown): Extract<LigneDuFil, { genre: "action" }> => ({
    genre: "action", id: "a1", nom: "reglages_regler", arguments: {}, fini: true, ok: true, resultat: { ok: true, journal },
});

describe("Annuler sur la ligne d'action", () => {
    it("un clic défait l'action, le dit, et la ligne devient « Annulée »", async () => {
        m.annuler.mockResolvedValue({ data: { ok: true } });
        render(<LigneAction ligne={ligne({ id: 7, annulable: true })} />);
        fireEvent.click(document.querySelector("[data-annuler-action='7']") as HTMLElement);
        await waitFor(() => expect(document.querySelector("[data-journal-annulee]")).not.toBeNull());
        expect(m.annuler.mock.calls[0][0]).toEqual({ path: { ligne_id: 7 } });
        expect(m.succes).toHaveBeenCalled();
    });

    it("un refus du serveur (une écriture plus récente) le dit et laisse le bouton", async () => {
        m.annuler.mockResolvedValue({ error: { detail: { code: "ordre", message: "x" } } });
        render(<LigneAction ligne={ligne({ id: 8, annulable: true })} />);
        fireEvent.click(document.querySelector("[data-annuler-action='8']") as HTMLElement);
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(document.querySelector("[data-annuler-action='8']")).not.toBeNull();
    });

    it("une action qui ne se défait pas dit pourquoi, sans bouton", () => {
        render(<LigneAction ligne={ligne({ id: 9, annulable: false, raison: "publication" })} />);
        expect(document.querySelector("[data-annuler-action]")).toBeNull();
        expect(document.querySelector("[data-journal-definitif='publication']")).not.toBeNull();
    });

    it("sans journal (une lecture), la ligne n'ajoute rien", () => {
        render(<LigneAction ligne={{ ...ligne(undefined), resultat: { ok: true } }} />);
        expect(document.querySelector("[data-journal-definitif],[data-annuler-action],[data-journal-annulee]")).toBeNull();
    });

    it("l'événement journal_annule marque la ligne, aussi après un rechargement du fil", () => {
        const avant: LigneDuFil[] = [ligne({ id: 7, annulable: true })];
        const apres = appliquer(avant, 5, { type: "journal_annule", id: 7 });
        render(<LigneAction ligne={apres[0] as Extract<LigneDuFil, { genre: "action" }>} />);
        expect(document.querySelector("[data-journal-annulee]")).not.toBeNull();
        expect(appliquer(avant, 6, { type: "journal_annule", id: 99 })).toEqual(avant);
    });
});

describe("le journal du builder", () => {
    const l = (id: number, extra: object = {}) => ({
        id, quand: new Date().toISOString(), workflow_id: 3, fil_id: 1, auteur: "c", porte: "ecran", action: `a${id}`, famille: "brouillon", mode: "tout",
        autorisation: "mode", statut: "fait", annulable: true, non_annulable: null, annule_le: null, annule_par: null, ...extra,
    });

    it("liste qui, quoi, mode et autorisation, pagine de 25 en 25", async () => {
        m.lire.mockResolvedValue({ data: { lignes: [l(2), l(1, { annulable: false, non_annulable: "depense", famille: "depense" })], total: 60, limit: 25, offset: 0 } });
        render(<JournalDuBuilder />);
        await screen.findByText("a2");
        expect(m.lire.mock.calls[0][0]).toEqual({ query: { limit: 25, offset: 0 } });
        expect(document.querySelector("[data-annuler-action='2']")).not.toBeNull();
        expect(document.querySelector("[data-journal-definitif='depense']")).not.toBeNull();
        m.lire.mockResolvedValue({ data: { lignes: [l(0)], total: 60, limit: 25, offset: 25 } });
        fireEvent.click(screen.getByLabelText("Older"));
        await waitFor(() => expect(m.lire.mock.calls.at(-1)?.[0]).toEqual({ query: { limit: 25, offset: 25 } }));
    });

    it("vide : le dit ; en erreur : propose de réessayer", async () => {
        m.lire.mockResolvedValue({ data: { lignes: [], total: 0, limit: 25, offset: 0 } });
        render(<JournalDuBuilder />);
        await screen.findByText("The builder has written nothing yet");
        cleanup();
        m.lire.mockResolvedValue({ error: {} });
        render(<JournalDuBuilder />);
        await screen.findByText("Try again");
    });
});
