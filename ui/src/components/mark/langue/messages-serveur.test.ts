/** [.mark] Clôture, SA-3 : un message du serveur se rend par identifiant dans les deux langues ; un code inconnu garde la phrase du serveur. */
import { describe, expect, it } from "vitest";

import { MESSAGES_SERVEUR, messageDuServeur, phraseDuServeur } from "./messages-serveur";

describe("messages du serveur par identifiant", () => {
    it("rend la phrase dans la langue, paramètres posés", () => {
        const d = { code: "test_jamais_rejoue", parametres: { nom: "Client mécontent" } };
        expect(messageDuServeur(d, "fr")).toBe("Client mécontent : jamais rejoué");
        expect(messageDuServeur(d, "en")).toBe("Client mécontent: never replayed");
        expect(messageDuServeur({ code: "longueur", parametres: { longueur: 900, plafond: 500 } }, "fr")).toContain("900");
    });

    it("choisit la phrase du cas et traduit le genre de valeur", () => {
        expect(messageDuServeur({ code: "etape_sans_sortie", parametres: { cas: "pas_de_fin" } }, "fr")).toBe("Le graphe n'a aucune étape de fin.");
        expect(messageDuServeur({ code: "exemple_de_valeur", parametres: { genre: "a date" } }, "fr")).toBe("Le prompt donne une date en exemple : le modèle le recopie.");
    });

    it("compose l'étape selon la forme", () => {
        const base = { code: "sortie_non_citee", etape: "Accueil" };
        expect(messageDuServeur({ ...base, forme: "prefixe" }, "fr")).toMatch(/^Accueil · L'étape a plusieurs sorties/);
        expect(messageDuServeur({ ...base, forme: "suffixe" }, "en")).toMatch(/\[Accueil\]$/);
    });

    it("un code inconnu ou absent garde la phrase du serveur", () => {
        expect(phraseDuServeur("Raw server text", { code: "inconnu" }, "fr")).toBe("Raw server text");
        expect(phraseDuServeur("Raw server text", undefined, "fr")).toBe("Raw server text");
    });

    it("chaque entrée a ses deux langues", () => {
        for (const [code, texte] of Object.entries(MESSAGES_SERVEUR)) {
            expect(texte.fr.length, code).toBeGreaterThan(3);
            expect(texte.en.length, code).toBeGreaterThan(3);
            expect(texte.fr, code).not.toBe(texte.en);
        }
    });
});

describe("lot 26 (M23) : T5 et T6 par identifiant", () => {
    it("T5 dit le logiciel ; T6 choisit sa phrase par règle et pose les champs obligatoires", () => {
        expect(messageDuServeur({ code: "systeme_sans_outil", parametres: { connecteur: "hubrise" } }, "fr")).toContain("(hubrise)");
        expect(messageDuServeur({ code: "description_d_outil", parametres: { regle: "interdiction" } }, "fr")).toContain("interdit au lieu de dire quoi faire");
        expect(messageDuServeur({ code: "description_d_outil", parametres: { regle: "obligatoire", champs: ["taille", "telephone"] } }, "fr")).toContain("(taille, telephone)");
        expect(messageDuServeur({ code: "description_d_outil", parametres: { regle: "exemple", genre: "a date" } }, "en")).toContain("a date as an example");
    });
});
