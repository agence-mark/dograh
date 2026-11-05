/**
 * [.mark] Partie 3, N1 (SA-N1a) : les permissions du builder dans le chat.
 *
 * Questions : la carte n'envoie-t-elle rien avant un clic, et envoie-t-elle la bonne décision (une fois, pour ce chat, refuser avec sa
 * raison) ? Une suppression montre-t-elle « Définitif » ? « Tout permettre » attend-il la confirmation centrée ? Le mode Plan est-il
 * proposé et son bandeau offre-t-il d'approuver le plan ? Une autorisation « pour ce chat » se retire-t-elle ? La réponse garde-t-elle la
 * carte à sa place ?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { appliquer, type LigneDuFil } from "./evenements";
import { BandeauMode, CarteAutorisation, libelleObjet, SelecteurMode } from "./permissions-du-chat";

// Le placement du menu (Radix) observe sa taille : jsdom n'a pas de ResizeObserver.
vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

afterEach(() => cleanup());

const carte = {
    type: "autorisation",
    id: "a1",
    action: "agent_publier",
    famille: "publication",
    objet: "agent:42",
    apres: { workflow_id: 42 },
    definitif: false,
    depense: false,
    statut: "attente",
};

describe("carte d'autorisation", () => {
    it("n'envoie rien avant un clic, puis la décision choisie", () => {
        const repondre = vi.fn();
        render(<CarteAutorisation carte={carte} active repondre={repondre} agentOuvert={42} />);
        expect(screen.getByText("Publish the agent")).toBeTruthy();
        expect(screen.getByText("This agent")).toBeTruthy();
        expect(screen.getByText("Publishing")).toBeTruthy();
        expect(screen.queryByText("Final")).toBeNull();
        expect(screen.queryByText(/workflow_id/)).toBeNull(); // l'agent visé est dit par l'objet, pas répété dans l'après
        expect(repondre).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Allow once" }));
        expect(repondre).toHaveBeenLastCalledWith("une_fois");
        fireEvent.click(screen.getByRole("button", { name: "Allow for this chat" }));
        expect(repondre).toHaveBeenLastCalledWith("pour_ce_chat");
    });

    it("refuser demande une raison facultative que le builder lit", () => {
        const repondre = vi.fn();
        render(<CarteAutorisation carte={carte} active repondre={repondre} />);
        fireEvent.click(screen.getByRole("button", { name: "Refuse" }));
        expect(repondre).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText("Reason for refusing"), { target: { value: "Pas avant lundi" } });
        fireEvent.click(screen.getByRole("button", { name: "Confirm the refusal" }));
        expect(repondre).toHaveBeenCalledWith("refuser", "Pas avant lundi");
    });

    it("une suppression montre « Définitif », une dépense son coût, et une carte inactive ne se clique pas", () => {
        const repondre = vi.fn();
        render(<CarteAutorisation carte={{ ...carte, action: "agent_archiver", famille: "irreversible", definitif: true, depense: true }} active={false} repondre={repondre} />);
        expect(screen.getByText("Final")).toBeTruthy();
        expect(screen.getByText(/runs paid models/)).toBeTruthy();
        expect((screen.getByRole("button", { name: "Allow once" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("une carte répondue dit son état, sans bouton", () => {
        render(<CarteAutorisation carte={{ ...carte, statut: "pour_ce_chat" }} active repondre={vi.fn()} />);
        expect(screen.getByText(/allowed for this chat/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Allow once" })).toBeNull();
    });

    it("l'objet se lit : cet agent, un autre agent, l'organisation", () => {
        expect(libelleObjet("agent:42", 42).en).toBe("This agent");
        expect(libelleObjet("agent:77", 42).en).toBe("Agent 77");
        expect(libelleObjet("organisation", 42).en).toBe("The organisation");
    });
});

describe("sélecteur de mode", () => {
    it("propose les quatre modes ; « Tout permettre » attend la confirmation centrée", async () => {
        const choisir = vi.fn();
        render(<SelecteurMode mode="demander" choisir={choisir} autorisations={[]} retirer={vi.fn()} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder permissions : Ask" }));
        expect(await screen.findByText("Allow everything on this agent")).toBeTruthy();
        expect(screen.getByText("Plan")).toBeTruthy();
        fireEvent.click(screen.getByText("Allow everything"));
        expect(choisir).not.toHaveBeenCalled();
        expect(await screen.findByText("Allow everything in this chat?")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
        expect(choisir).toHaveBeenCalledWith("tout");
    });

    it("choisit « Tout permettre sur cet agent » et « Plan » sans confirmation", async () => {
        const choisir = vi.fn();
        render(<SelecteurMode mode="demander" choisir={choisir} autorisations={[]} retirer={vi.fn()} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder permissions : Ask" }));
        fireEvent.click(await screen.findByText("Allow everything on this agent"));
        expect(choisir).toHaveBeenLastCalledWith("agent");
        fireEvent.click(screen.getByRole("button", { name: "Builder permissions : Ask" }));
        fireEvent.click((await screen.findAllByText("Plan"))[0]);
        expect(choisir).toHaveBeenLastCalledWith("plan");
    });

    it("liste les autorisations « pour ce chat » et les retire", async () => {
        const retirer = vi.fn();
        render(<SelecteurMode mode="agent" choisir={vi.fn()} autorisations={[{ id: "a3", nom: "agent_publier", objet: "agent:42" }]} retirer={retirer} agentOuvert={42} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder permissions : Allow everything on this agent" }));
        expect(await screen.findByText(/Publish the agent · This agent/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Withdraw the permission" }));
        expect(retirer).toHaveBeenCalledWith("a3");
    });
});

describe("bandeau du mode", () => {
    it("rien en « Demander » ; en Plan, approuver le plan ou revenir", () => {
        const { container, rerender } = render(<BandeauMode mode="demander" revenir={vi.fn()} approuverLePlan={vi.fn()} />);
        expect(container.querySelector("[data-bandeau-mode]")).toBeNull();
        const approuver = vi.fn();
        const revenir = vi.fn();
        rerender(<BandeauMode mode="plan" revenir={revenir} approuverLePlan={approuver} />);
        fireEvent.click(screen.getByRole("button", { name: "Approve the plan" }));
        fireEvent.click(screen.getByRole("button", { name: "Back to « Ask »" }));
        expect(approuver).toHaveBeenCalledOnce();
        expect(revenir).toHaveBeenCalledOnce();
    });
});

describe("le fil", () => {
    it("la réponse garde la carte à sa place et la fin « attente » n'ajoute pas de ligne", () => {
        let lignes: LigneDuFil[] = [];
        lignes = appliquer(lignes, 1, { type: "carte", carte });
        lignes = appliquer(lignes, 2, { type: "fin", raison: "attente" });
        expect(lignes).toHaveLength(1);
        lignes = appliquer(lignes, 3, { type: "autorisation_reponse", id: "a1", statut: "une_fois" });
        expect(lignes).toHaveLength(1);
        expect(lignes[0].genre === "carte" && lignes[0].carte.statut).toBe("une_fois");
    });
});
