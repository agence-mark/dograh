/**
 * [.mark] V5 : les données de l'éditeur du widget.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | couleurs | la règle de couleur est celle du serveur (`test_site_editeur_v5.py`) : mêmes défauts, texte lisible, rouge de raccrocher |
 * | retouche | une retouche ne touche aucune autre ; `fenetreTexte` est le texte de base |
 * | bleu .mark | revient au bleu, à l'orbe, aux bases, sans retouche, textes gardés |
 * | bornes | les bornes de texte sont celles du serveur |
 * | zones | chaque zone a de quoi se régler (une couleur ou un texte) sur une clé qui existe |
 */
import { describe, expect, it } from "vitest";

import { adresseValide, auBleuMark, avecCouleur, avecTexte, COULEURS, couleursResolues, declenchementDe, erreurDeTexte, texteSur,ZONES } from "./editeur-donnees";

describe("la règle de couleur", () => {
    it("donne les mêmes défauts que le serveur", () => {
        const k = couleursResolues({});
        expect(k.raccrocherFond).toBe("#dc2626");
        expect(k.raccrocherTexte).toBe("#ffffff");
        expect(k.bulleAgentFond).toBe("#f1f1f1");
        expect(k.boutonTexte).toBe("#ffffff");
        expect(k.saisieTexte).toBe("#0f1c2e");
        expect(Object.keys(k)).toHaveLength(Object.keys(COULEURS).length);
    });

    it("met un texte lisible sur le fond : noir sur jaune, blanc sur bleu", () => {
        expect(texteSur("#ffffff")).toBe("#111111");
        expect(texteSur("#1b5fb0")).toBe("#ffffff");
        expect(couleursResolues({ couleur_base: "#ffe600" }).boutonTexte).toBe("#111111");
    });

    it("une retouche ne touche aucune autre couleur", () => {
        const base = couleursResolues({});
        const ap = avecCouleur({}, "boutonTexte", "#00ff00");
        const k = couleursResolues(ap);
        expect(k.boutonTexte).toBe("#00ff00");
        expect({ ...k, boutonTexte: 0 }).toEqual({ ...base, boutonTexte: 0 });
        // le texte de la fenêtre est un champ de base
        expect(avecCouleur({}, "fenetreTexte", "#123456").texte_fenetre).toBe("#123456");
    });
});

describe("revenir au bleu .mark", () => {
    it("efface les retouches et l'emblème, garde les textes", () => {
        const ap = avecTexte(avecCouleur({ couleur_base: "#c2410c", embleme: "logo" }, "orbe", "#000000"), "accroche", "Bonjour");
        const neuf = auBleuMark(ap);
        expect(neuf.couleur_base).toBe("#1b5fb0");
        expect(neuf.couleurs).toEqual({});
        expect(neuf.embleme).toBe("orbe");
        expect(neuf.textes?.accroche).toBe("Bonjour");
    });
});

describe("les bornes du serveur", () => {
    it("accroche : 3 lignes et 120 caractères ; autres textes : 200 ; jamais vide", () => {
        expect(erreurDeTexte("accroche", "a\nb\nc\nd")).toBe("lignes");
        expect(erreurDeTexte("accroche", "x".repeat(121))).toBe("long");
        expect(erreurDeTexte("accroche", "a\nb\nc")).toBeNull();
        expect(erreurDeTexte("merci", "x".repeat(201))).toBe("long");
        expect(erreurDeTexte("merci", "  ")).toBe("vide");
    });
    it("une adresse commence par https://", () => {
        expect(adresseValide("")).toBe(true);
        expect(adresseValide("https://a.fr/x")).toBe(true);
        expect(adresseValide("http://a.fr")).toBe(false);
        expect(adresseValide("javascript:alert(1)")).toBe(false);
    });
    it("l'ancien « clic » se lit « survol »", () => {
        expect(declenchementDe({ declenchement: "clic" })).toBe("survol");
        expect(declenchementDe({ declenchement: "toujours" })).toBe("toujours");
    });
});

describe("les zones", () => {
    it("chacune se règle (une couleur ou un texte) et ses couleurs existent", () => {
        for (const [nom, z] of Object.entries(ZONES)) {
            expect((z.couleurs?.length ?? 0) + (z.textes?.length ?? 0) + (z.embleme ? 1 : 0), nom).toBeGreaterThan(0);
            for (const c of z.couleurs ?? []) expect(COULEURS, nom).toHaveProperty(c.cle);
        }
    });
    it("couvre les repères du vrai widget", () => {
        for (const repere of ["rond", "accroche", "fenetre", "titre", "orbe", "information", "demarrer", "plafond", "plafondBouton", "microRefuse", "bulleAgent", "bulleVisiteur", "raccrocher", "saisieVoix", "saisieEcrite", "envoyer", "avisTitre", "avisQuestion", "etoiles", "choix", "caseRappel", "casePublication", "avisPasser", "avisEnvoyer", "merciIcone", "merci", "fermer"]) {
            expect(ZONES, repere).toHaveProperty(repere);
        }
    });
});
