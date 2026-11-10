/**
 * [.mark] Correctifs d'écran, point 15 : le logo d'un client dans Réglages › Général.
 *
 * Questions de ce fichier :
 *
 *     Un format refusé (SVG, GIF renommé en .png) et un fichier trop lourd sont-ils refusés À L'ÉCRAN, sous le champ, sans rien envoyer ?
 *     Des dimensions ou un ratio hors bornes aussi ? Une image valide part au serveur et dit son succès ? L'aperçu montre le logo
 *     quand il y en a un, l'initiale sinon, et retombe sur l'initiale si l'image ne charge pas ? « Retirer » demande confirmation
 *     puis retire ? Le contrôle de l'écran lit-il le type dans les octets plutôt que dans le nom ?
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    poser: vi.fn(),
    retirer: vi.fn(),
    lire: vi.fn(),
    succes: vi.fn(),
    echec: vi.fn(),
}));

vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));
vi.mock("@/client/sdk.gen", () => ({ lireLeLogoApiV1EspacesOrganizationIdLogoGet: (o: unknown) => m.lire(o) }));
vi.mock("@/lib/espaces", () => ({
    poserLogo: (id: number, f: File) => m.poser(id, f),
    retirerLogo: (id: number) => m.retirer(id),
    ErreurLogoServeur: class extends Error {
        constructor(
            readonly statut: number,
            readonly code: string,
        ) {
            super(code);
        }
    },
}));

import { controlerLogo, LOGO_OCTETS_MAX } from "@/lib/logo-controle";
import { memoriserLogos, oublierLesLogos } from "@/lib/logos-espaces";

import { FournisseurLangue } from "../langue/langue";
import { LigneLogoOrganisation } from "./LigneLogoOrganisation";

/** Un PNG « d'en-tête » : signature + IHDR de la taille donnée, ce que le contrôle lit. */
function entetePng(largeur: number, hauteur: number): Uint8Array {
    const o = new Uint8Array(33);
    o.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]);
    new DataView(o.buffer).setUint32(16, largeur);
    new DataView(o.buffer).setUint32(20, hauteur);
    return o;
}
const fichier = (octets: BlobPart, nom = "logo.png", type = "image/png") => new File([octets], nom, { type });

beforeEach(() => {
    oublierLesLogos();
    m.poser.mockReset().mockResolvedValue({ id: 2, logo_version: "v1" });
    m.retirer.mockReset().mockResolvedValue({ id: 2, logo_version: null });
    m.lire.mockReset().mockResolvedValue({ data: new Blob(["x"], { type: "image/png" }), error: undefined });
    m.succes.mockReset();
    m.echec.mockReset();
    URL.createObjectURL = vi.fn(() => "blob:logo-2");
    URL.revokeObjectURL = vi.fn();
});
afterEach(cleanup);

const monter = () =>
    render(
        <FournisseurLangue>
            <LigneLogoOrganisation id={2} nom="Atelier des Tilleuls" />
        </FournisseurLangue>,
    );
const choisir = async (f: File) => {
    await act(async () => {
        fireEvent.change(screen.getByTestId("logo-fichier"), { target: { files: [f] } });
    });
};
const erreur = () => document.querySelector("[data-erreur-logo]")?.textContent ?? null;

describe("le contrôle de l'écran, avant l'envoi", () => {
    it("refuse un SVG et un GIF renommé en .png, sans rien envoyer", async () => {
        monter();
        await choisir(fichier('<svg xmlns="http://www.w3.org/2000/svg"></svg>', "logo.svg", "image/svg+xml"));
        expect(erreur()).toMatch(/pas de SVG/);
        await choisir(fichier("GIF89a" + "x".repeat(200), "logo.png", "image/png"));
        expect(erreur()).toMatch(/Format non accepté/);
        expect(m.poser).not.toHaveBeenCalled();
    });

    it("refuse un fichier de plus de 1 Mo", async () => {
        monter();
        await choisir(fichier(new Uint8Array(LOGO_OCTETS_MAX + 1)));
        expect(erreur()).toMatch(/dépasse 1 Mo/);
        expect(m.poser).not.toHaveBeenCalled();
    });

    it("refuse des dimensions ou un ratio hors bornes", async () => {
        monter();
        await choisir(fichier(entetePng(64, 64)));
        expect(erreur()).toMatch(/de 128 à 1024 px/);
        await choisir(fichier(entetePng(640, 400)));
        expect(erreur()).toMatch(/presque carrée/);
        expect(m.poser).not.toHaveBeenCalled();
    });

    it("lit le type dans les octets : un faux nom ne passe pas, un bon contenu passe", () => {
        expect(controlerLogo(entetePng(512, 512))).toMatchObject({ ok: true, format: "png", largeur: 512, hauteur: 512 });
        expect(controlerLogo(new TextEncoder().encode("ceci n'est pas une image"))).toEqual({ ok: false, code: "logo_format" });
    });
});

describe("l'envoi, l'aperçu et le retrait", () => {
    it("envoie une image valide et le dit par une notification", async () => {
        monter();
        const f = fichier(entetePng(512, 512));
        await choisir(f);
        await waitFor(() => expect(m.poser).toHaveBeenCalledWith(2, f));
        expect(m.succes).toHaveBeenCalled();
        expect(erreur()).toBeNull();
    });

    it("dit sous le champ un refus du serveur (jamais son texte brut) et notifie une panne", async () => {
        const { ErreurLogoServeur } = await import("@/lib/espaces");
        monter();
        m.poser.mockRejectedValueOnce(new ErreurLogoServeur(422, "logo_ratio"));
        await choisir(fichier(entetePng(512, 512)));
        await waitFor(() => expect(erreur()).toMatch(/presque carrée/));
        m.poser.mockRejectedValueOnce(new Error("boom <stack>"));
        await choisir(fichier(entetePng(512, 512)));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(document.body.textContent).not.toMatch(/boom|stack/);
    });

    it("sans logo : l'initiale et « Ajouter un logo » ; avec logo : l'image et « Remplacer »", async () => {
        monter();
        expect(document.querySelector("[data-logo-client]")).toBeNull();
        expect(screen.getByRole("button", { name: /Ajouter un logo/ })).toBeTruthy();
        expect(screen.getByText("AD")).toBeTruthy();
        await act(async () => memoriserLogos([{ id: 2, logo_version: "v1" }]));
        await waitFor(() => expect(document.querySelector("[data-logo-client]")).not.toBeNull());
        expect(m.lire).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("button", { name: /Remplacer/ })).toBeTruthy();
        expect(screen.queryByText("AD")).toBeNull();
    });

    it("retombe sur l'initiale quand l'image ne charge pas", async () => {
        monter();
        await act(async () => memoriserLogos([{ id: 2, logo_version: "v1" }]));
        const img = await waitFor(() => {
            const el = document.querySelector("[data-logo-client]");
            expect(el).not.toBeNull();
            return el as HTMLElement;
        });
        await act(async () => {
            fireEvent.error(img);
        });
        expect(document.querySelector("[data-logo-client]")).toBeNull();
        expect(screen.getByText("AD")).toBeTruthy();
    });

    it("retombe sur l'initiale quand la lecture du logo échoue", async () => {
        m.lire.mockResolvedValue({ data: undefined, error: { detail: "x" } });
        monter();
        await act(async () => memoriserLogos([{ id: 2, logo_version: "v1" }]));
        await waitFor(() => expect(m.lire).toHaveBeenCalled());
        expect(document.querySelector("[data-logo-client]")).toBeNull();
        expect(screen.getByText("AD")).toBeTruthy();
    });

    it("« Retirer » demande confirmation, puis retire", async () => {
        monter();
        await act(async () => memoriserLogos([{ id: 2, logo_version: "v1" }]));
        await waitFor(() => screen.getByRole("button", { name: /Retirer/ }));
        fireEvent.click(screen.getByRole("button", { name: /Retirer/ }));
        expect(m.retirer).not.toHaveBeenCalled();
        expect(screen.getByText("Retirer le logo ?")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Garder" }));
        expect(m.retirer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: /Retirer/ }));
        await act(async () => {
            fireEvent.click(screen.getAllByRole("button", { name: "Retirer" }).at(-1)!);
        });
        expect(m.retirer).toHaveBeenCalledWith(2);
        expect(m.succes).toHaveBeenCalled();
    });
});
