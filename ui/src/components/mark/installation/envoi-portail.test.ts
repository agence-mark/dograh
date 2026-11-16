/**
 * [.mark] M40 : le formulaire qui porte la fiche au portail.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | formulaire | POST de premier niveau vers `/relier/auto` du portail, dans l'onglet ouvert au clic ; la fiche est dans le corps, jamais dans l'adresse ; le formulaire est retiré aussitôt |
 * | sans onglet | le navigateur a refusé l'onglet : le formulaire part dans un nouvel onglet |
 * | onglet | l'onglet est coupé de la page d'origine (`opener` à rien) |
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/mark/relation/commun", () => ({ ADRESSE_PORTAIL: "https://portail.test" }));

const { ouvrirOngletDuPortail, posterAuPortail } = await import("./envoi-portail");

const corps = { fiche: '{"cle_api":{"valeur":"cle-SECRETE"}}', lien: "77.jeton", nom: "Casa", montage: "un", canaux: "telephone", metier: "restauration" };

afterEach(() => vi.restoreAllMocks());

describe("envoi au portail", () => {
    it("poste un formulaire caché dans l'onglet, la fiche dans le corps seulement", () => {
        let vu: HTMLFormElement | null = null;
        vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function (this: HTMLFormElement) {
            vu = this.cloneNode(true) as HTMLFormElement;
        });
        posterAuPortail({ name: "portail-client-77" } as Window, corps);
        expect(vu).not.toBeNull();
        const f = vu as unknown as HTMLFormElement;
        expect(f.method).toBe("post");
        expect(f.action).toBe("https://portail.test/relier/auto");
        expect(f.target).toBe("portail-client-77");
        expect(Object.fromEntries(new FormData(f).entries())).toEqual(corps);
        expect(f.action).not.toContain("SECRETE");
        expect(document.querySelector("form")).toBeNull();
    });

    it("sans onglet, un nouvel onglet", () => {
        let cible = "";
        vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function (this: HTMLFormElement) {
            cible = this.target;
        });
        posterAuPortail(null, corps);
        expect(cible).toBe("_blank");
    });

    it("ouvre l'onglet nommé et le coupe de la page d'origine", () => {
        const onglet = { name: "portail-client-77", opener: {} } as unknown as Window;
        const ouvrir = vi.spyOn(window, "open").mockReturnValue(onglet);
        expect(ouvrirOngletDuPortail(77)).toBe(onglet);
        expect(ouvrir).toHaveBeenCalledWith("", "portail-client-77");
        expect(onglet.opener).toBeNull();
    });
});
