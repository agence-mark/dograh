/**
 * [.mark] Notifications passagères : le magasin (durées, pile, regroupement, minuterie suspendue).
 * Règles tranchées par Evan le 04/11 (`15-notifications.md`).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ajouter, DUREES, fermer, lireNotifications, remplacer, reprendre, suspendre, viderNotifications, VISIBLES_AU_PLUS } from "./magasin";

const texte = (s: string) => ({ fr: s, en: s });

beforeEach(() => {
    vi.useFakeTimers();
    viderNotifications();
});
afterEach(() => {
    viderNotifications();
    vi.useRealTimers();
});

describe("durées", () => {
    it("succès et information 4 s, avertissement 8 s, échec reste jusqu'à fermeture", () => {
        expect(DUREES).toMatchObject({ succes: 4000, information: 4000, avertissement: 8000, echec: null, encours: null });
        ajouter({ sorte: "succes", texte: texte("a") });
        ajouter({ sorte: "avertissement", texte: texte("b") });
        ajouter({ sorte: "echec", texte: texte("c") });
        vi.advanceTimersByTime(3999);
        expect(lireNotifications()).toHaveLength(3);
        vi.advanceTimersByTime(1);
        expect(lireNotifications().map((n) => n.sorte)).toEqual(["avertissement", "echec"]);
        vi.advanceTimersByTime(4000);
        expect(lireNotifications().map((n) => n.sorte)).toEqual(["echec"]);
        vi.advanceTimersByTime(10 * 60 * 1000);
        expect(lireNotifications().map((n) => n.sorte)).toEqual(["echec"]);
    });
});

describe("regroupement", () => {
    it("une même action répétée remplace au lieu d'empiler", () => {
        ajouter({ sorte: "succes", texte: texte("Clé copiée.") });
        ajouter({ sorte: "succes", texte: texte("Clé copiée.") });
        ajouter({ sorte: "succes", texte: texte("Clé copiée.") });
        expect(lireNotifications()).toHaveLength(1);
    });

    it("la minuterie repart à zéro à chaque répétition", () => {
        ajouter({ sorte: "succes", texte: texte("Clé copiée.") });
        vi.advanceTimersByTime(3000);
        ajouter({ sorte: "succes", texte: texte("Clé copiée.") });
        vi.advanceTimersByTime(3000);
        expect(lireNotifications()).toHaveLength(1);
        vi.advanceTimersByTime(1000);
        expect(lireNotifications()).toHaveLength(0);
    });

    it("des textes différents coexistent ; un groupe explicite regroupe des textes différents", () => {
        ajouter({ sorte: "succes", texte: texte("a") });
        ajouter({ sorte: "succes", texte: texte("b") });
        expect(lireNotifications()).toHaveLength(2);
        ajouter({ sorte: "echec", texte: texte("x"), groupe: "g" });
        ajouter({ sorte: "echec", texte: texte("y"), groupe: "g" });
        expect(lireNotifications().filter((n) => n.groupe === "g").map((n) => n.texte.fr)).toEqual(["y"]);
    });
});

describe("pile", () => {
    it("trois visibles au plus : les plus récentes", () => {
        expect(VISIBLES_AU_PLUS).toBe(3);
        for (const s of ["a", "b", "c", "d"]) ajouter({ sorte: "echec", texte: texte(s) });
        expect(lireNotifications()).toHaveLength(4);
        expect(lireNotifications().slice(-VISIBLES_AU_PLUS).map((n) => n.texte.fr)).toEqual(["b", "c", "d"]);
    });
});

describe("minuterie suspendue au survol et au focus", () => {
    it("ne tourne pas tant qu'on survole, reprend avec le temps qui restait", () => {
        const cle = ajouter({ sorte: "succes", texte: texte("a") });
        vi.advanceTimersByTime(3000);
        suspendre(cle);
        vi.advanceTimersByTime(60_000);
        expect(lireNotifications()).toHaveLength(1);
        reprendre(cle);
        vi.advanceTimersByTime(999);
        expect(lireNotifications()).toHaveLength(1);
        vi.advanceTimersByTime(1);
        expect(lireNotifications()).toHaveLength(0);
    });

    it("souris et clavier se cumulent : elle ne repart que quand les deux ont quitté", () => {
        const cle = ajouter({ sorte: "succes", texte: texte("a") });
        suspendre(cle);
        suspendre(cle);
        reprendre(cle);
        vi.advanceTimersByTime(60_000);
        expect(lireNotifications()).toHaveLength(1);
        reprendre(cle);
        vi.advanceTimersByTime(4000);
        expect(lireNotifications()).toHaveLength(0);
    });
});

describe("changement d'état", () => {
    it("« en cours » devient succès dans la même place, avec une minuterie neuve", () => {
        const a = ajouter({ sorte: "encours", texte: texte("Publication en cours…") });
        ajouter({ sorte: "information", texte: texte("autre") });
        remplacer(a, { sorte: "succes", texte: texte("Agent publié.") });
        expect(lireNotifications().map((n) => n.texte.fr)).toEqual(["Agent publié.", "autre"]);
        vi.advanceTimersByTime(4000);
        expect(lireNotifications()).toHaveLength(0);
    });

    it("fermer retire la notification et arrête sa minuterie", () => {
        const cle = ajouter({ sorte: "succes", texte: texte("a") });
        fermer(cle);
        expect(lireNotifications()).toHaveLength(0);
        expect(vi.getTimerCount()).toBe(0);
    });
});
