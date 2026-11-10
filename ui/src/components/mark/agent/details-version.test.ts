/**
 * [.mark] Clôture, É36 : les trois colonnes de la page Versions, en français et en anglais, « – » pour une version d'avant.
 */
import { describe, expect, it } from "vitest";

import { libelleDeLAuteur, libelleDesTests, phraseDesChangements, VIDE } from "./details-version";

const resume = { total: 5, etapes_ajoutees: 1, noms_ajoutees: ["Rendez-vous"], etapes_retirees: 0, etapes_modifiees: 4, noms_modifiees: ["A", "B", "C"], liaisons: 2, reglages: 1 };

describe("phraseDesChangements", () => {
    it("écrit la phrase dans la langue de l'écran, avec les premiers noms", () => {
        expect(phraseDesChangements(resume, "fr")).toBe("1 étape ajoutée (Rendez-vous), 4 étapes modifiées (A, B, C…), 2 liaisons, 1 réglage");
        expect(phraseDesChangements(resume, "en")).toBe("1 step added (Rendez-vous), 4 steps changed (A, B, C…), 2 links, 1 setting");
    });
    it("dit « Aucun changement » pour une version identique et « – » sans résumé", () => {
        expect(phraseDesChangements({ total: 0 }, "fr")).toBe("Aucun changement");
        expect(phraseDesChangements(null, "fr")).toBe(VIDE);
        expect(phraseDesChangements(undefined, "en")).toBe(VIDE);
        expect(phraseDesChangements({ total: 3 }, "en")).toBe(VIDE);
    });
});

describe("libelleDeLAuteur", () => {
    const base = { accepte_par: false, accepte_par_nom: null, auteur_nom: null };
    it("nomme le builder, la personne et la clé", () => {
        expect(libelleDeLAuteur({ ...base, auteur_type: "builder" }, "fr")).toBe("Builder");
        expect(libelleDeLAuteur({ ...base, auteur_type: "personne", auteur_nom: "Evan" }, "fr")).toBe("Evan");
        expect(libelleDeLAuteur({ ...base, auteur_type: "personne" }, "en")).toBe("A person");
        expect(libelleDeLAuteur({ ...base, auteur_type: "cle_api", auteur_nom: "Clé du portail" }, "fr")).toBe("Clé du portail");
    });
    it("ajoute qui a accepté", () => {
        expect(libelleDeLAuteur({ ...base, auteur_type: "builder", accepte_par: true, accepte_par_nom: "Pierre" }, "fr")).toBe("Builder, accepté par Pierre");
        expect(libelleDeLAuteur({ ...base, auteur_type: "builder", accepte_par: true }, "en")).toBe("Builder, accepted by a person");
    });
    it("met « – » à une version d'avant", () => {
        expect(libelleDeLAuteur({ ...base, auteur_type: null }, "fr")).toBe(VIDE);
        expect(libelleDeLAuteur({ ...base }, "fr")).toBe(VIDE);
    });
});

describe("libelleDesTests", () => {
    it("écrit réussis/total, « – » sans compte", () => {
        expect(libelleDesTests({ tests_reussis: 21, tests_total: 24 })).toBe("21/24");
        expect(libelleDesTests({ tests_reussis: 0, tests_total: 3 })).toBe("0/3");
        expect(libelleDesTests({ tests_reussis: null, tests_total: null })).toBe(VIDE);
        expect(libelleDesTests({})).toBe(VIDE);
    });
});
