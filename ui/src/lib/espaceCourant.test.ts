/**
 * [.mark] U2 : l'organisation d'une requête se lit dans l'adresse de l'onglet.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
    definirLabo,
    adresseClientInvalide,
    entetesDeRequete,
    espaceDeAdresse,
    organisationPourRequete,
    organisationPourRequeteAttendue,
    preparerLabo,
    retenirEspace,
    sansOrganisation,
} from "./espaceCourant";

beforeEach(() => {
    window.sessionStorage.clear();
    definirLabo(null);
});

describe("espace d'une adresse", () => {
    it("un client se lit dans l'adresse, le Labo aussi, le reste est neutre", () => {
        expect(espaceDeAdresse("/clients/12/agents")).toBe(12);
        expect(espaceDeAdresse("/clients/12")).toBe(12);
        expect(espaceDeAdresse("/labo/agents")).toBe("labo");
        expect(espaceDeAdresse("/labo")).toBe("labo");
        expect(espaceDeAdresse("/agents/5")).toBeNull();
        expect(espaceDeAdresse("/clients/acme/agents")).toBeNull(); // pas un identifiant : jamais envoyé
        expect(espaceDeAdresse("/laboratoire")).toBeNull();
    });
});

describe("organisation d'une requête", () => {
    it("depuis un client : celle de l'adresse", () => {
        expect(organisationPourRequete("/clients/7/outils")).toBe(7);
    });

    it("depuis le Labo : l'identifiant du Labo, une fois connu", () => {
        expect(organisationPourRequete("/labo/agents")).toBeNull();
        definirLabo(3);
        expect(organisationPourRequete("/labo/agents")).toBe(3);
    });

    it("une adresse neutre garde l'espace de l'onglet (deux onglets, deux espaces)", () => {
        expect(organisationPourRequete("/agents/9")).toBeNull();
        retenirEspace("/clients/7/agents");
        expect(organisationPourRequete("/agents/9")).toBe(7);
        retenirEspace("/agents/9"); // une adresse neutre ne change rien
        expect(organisationPourRequete("/conversations/2")).toBe(7);
        definirLabo(3);
        retenirEspace("/labo");
        expect(organisationPourRequete("/agents/9")).toBe(3);
    });

    it("depuis le Labo, une requête attend l'identifiant du Labo", async () => {
        preparerLabo(async () => definirLabo(41));
        expect(await organisationPourRequeteAttendue("/labo/agents")).toBe(41);
        expect(await organisationPourRequeteAttendue("/clients/2")).toBe(2);
    });

    it("la lecture des espaces se fait sans organisation", () => {
        expect(sansOrganisation("http://api/api/v1/espaces")).toBe(true);
        expect(sansOrganisation("http://api/api/v1/espaces/conversations")).toBe(false);
        expect(sansOrganisation("http://api/api/v1/workflow/count")).toBe(false);
    });
});

describe("R3 M1 : le Labo inconnu ne retombe jamais sur un client", () => {
    it("depuis le Labo sans identifiant, la requête est refusée", async () => {
        preparerLabo(async () => {
            throw new Error("panne");
        });
        await expect(entetesDeRequete("/labo/agents")).rejects.toThrow();
    });

    it("un échec n'est pas gardé : la requête suivante relit les espaces", async () => {
        let appels = 0;
        preparerLabo(async () => {
            appels += 1;
            if (appels === 1) throw new Error("panne");
            definirLabo(5);
        });
        await expect(entetesDeRequete("/labo")).rejects.toThrow();
        expect(await entetesDeRequete("/labo")).toEqual({ "X-Mark-Espace": "labo", "X-Mark-Organisation": "5" });
        expect(appels).toBe(2);
    });

    it("un client illisible dans l'adresse est refusé, jamais remplacé par l'espace retenu", async () => {
        retenirEspace("/labo");
        definirLabo(3);
        expect(adresseClientInvalide("/clients/acme/agents")).toBe(true);
        expect(adresseClientInvalide("/clients/12/agents")).toBe(false);
        await expect(entetesDeRequete("/clients/acme/agents")).rejects.toThrow();
        expect(await entetesDeRequete("/clients/12")).toEqual({ "X-Mark-Organisation": "12" });
    });
});
