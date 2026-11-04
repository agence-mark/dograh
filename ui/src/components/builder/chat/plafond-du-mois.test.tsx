/**
 * [.mark] Partie 3, sous-lot 11 (SE-16, E-5) : budget du mois atteint. Le serveur refuse un NOUVEAU travail (402) ; l'écran le dit
 * par une notification et propose « Continuer quand même », qui renvoie le MÊME geste avec le drapeau, une seule fois.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    envoyer: vi.fn(),
    lire: vi.fn(),
    avertissement: vi.fn(),
    echec: vi.fn(),
    succes: vi.fn(),
}));

vi.mock("@/client", () => ({
    arreterUnFilApiV1BuilderFilsFilIdArreterPost: vi.fn(),
    envoyerUnMessageApiV1BuilderFilsFilIdMessagesPost: (o: unknown) => m.envoyer(o),
    lireUnFilApiV1BuilderFilsFilIdGet: () => m.lire(),
    modifierLeDernierMessageApiV1BuilderFilsFilIdModifierDernierPost: vi.fn(),
    repondreAUneDepenseApiV1BuilderFilsFilIdDepensesDepenseIdPost: vi.fn(),
    reprendreUnFilApiV1BuilderFilsFilIdReprendrePost: vi.fn(),
    suivreUnFilApiV1BuilderFilsFilIdEvenementsGet: async () => ({ data: new ReadableStream({ start: (c) => c.close() }) }),
}));
const AUTH = vi.hoisted(() => ({ user: { id: "u" }, loading: false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: { avertissement: m.avertissement, echec: m.echec, succes: m.succes } }));
vi.mock("@/components/mark/notifications/echec-affiche", () => ({ ECHEC_DU_FIL: { en: "x", fr: "x" }, echecAffiche: () => "x" }));

import { FenetrePlafondDuMois } from "./plafond-du-mois";
import { useFil } from "./useFil";

afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const FIL = { id: 5, etat: "terminee", genre: "builder" };

function Essai() {
    const { envoyer, plafond, continuerQuandMeme, annulerLePlafond } = useFil(5);
    return (
        <>
            <button onClick={() => void envoyer("Bonjour")}>go</button>
            <FenetrePlafondDuMois ouverte={plafond !== null} enCours={plafond?.enCours ?? false} continuer={() => void continuerQuandMeme()} annuler={annulerLePlafond} />
        </>
    );
}

describe("plafond du mois dans le fil", () => {
    it("402 : notification et fenêtre, rien n'est dépassé avant le clic ; « Continuer quand même » renvoie le geste avec le drapeau", async () => {
        m.lire.mockResolvedValue({ data: FIL });
        m.envoyer.mockResolvedValueOnce({ error: { detail: "ceiling" }, response: { status: 402 } });
        render(<Essai />);
        await act(async () => fireEvent.click(screen.getByText("go")));
        await waitFor(() => expect(m.avertissement).toHaveBeenCalled());
        expect(m.envoyer).toHaveBeenCalledTimes(1);
        expect(m.envoyer.mock.calls[0][0].body).toEqual({ message: "Bonjour" });
        expect(document.querySelector("[data-fenetre-plafond-du-mois]")).not.toBeNull();
        m.envoyer.mockResolvedValueOnce({ data: FIL });
        fireEvent.click(document.querySelector("[data-continuer-quand-meme]") as HTMLElement);
        await waitFor(() => expect(m.envoyer).toHaveBeenCalledTimes(2));
        expect(m.envoyer.mock.calls[1][0].body).toEqual({ message: "Bonjour", depasser_le_plafond: true });
        await waitFor(() => expect(document.querySelector("[data-fenetre-plafond-du-mois]")).toBeNull());
    });

    it("Annuler ferme la fenêtre sans renvoyer ; un refus 403 dit que seule l'équipe .mark dépasse", async () => {
        m.lire.mockResolvedValue({ data: FIL });
        m.envoyer.mockResolvedValueOnce({ error: {}, response: { status: 402 } });
        render(<Essai />);
        await act(async () => fireEvent.click(screen.getByText("go")));
        fireEvent.click(await screen.findByText("Cancel"));
        await waitFor(() => expect(document.querySelector("[data-fenetre-plafond-du-mois]")).toBeNull());
        expect(m.envoyer).toHaveBeenCalledTimes(1);

        m.envoyer.mockResolvedValueOnce({ error: {}, response: { status: 402 } });
        await act(async () => fireEvent.click(screen.getByText("go")));
        m.envoyer.mockResolvedValueOnce({ error: {}, response: { status: 403 } });
        fireEvent.click(await waitFor(() => document.querySelector("[data-continuer-quand-meme]") as HTMLElement));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
    });
});
