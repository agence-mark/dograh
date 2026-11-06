/**
 * [.mark] K7 : le bandeau d'un chat dans la barre du haut (maquette `app/labo/builder/[id]`). Questions : le titre est-il le dernier
 * maillon du fil d'Ariane ? l'état, la jauge en cercle, « Arrêter » et « Ouvrir l'agent » sont-ils à droite ? « Arrêter » appelle-t-il
 * l'arrêt, « Reprendre » la reprise ? une conversation Claude Code montre-t-elle sa marque au lieu des boutons ?
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";
import { ShellStudio } from "@/components/mark/studio/shell-studio";

import { BandeauDuFil } from "./BandeauDuFil";

vi.mock("next/navigation", () => ({ usePathname: () => "/labo/builder/4", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ provider: "local", logout: vi.fn(), user: { email: "evan@exemple.fr" } }) }));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
    useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0 }),
}));
vi.mock("@/components/mark/studio/selecteur-espace", () => ({ SelecteurEspace: () => <div /> }));
vi.mock("@/components/layout/SidebarTeamSwitcher", () => ({ SidebarTeamSwitcher: () => <div /> }));
vi.mock("@/components/ThemeSwitcher", () => ({ default: () => <button type="button">thème</button> }));
vi.mock("@/components/mark/studio/nom-espace", () => ({ useNomEspace: () => null }));

window.matchMedia =
    window.matchMedia ||
    ((query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} }) as unknown as MediaQueryList);

afterEach(cleanup);

const fil = (plus: Record<string, unknown> = {}) =>
    ({ id: 4, workflow_id: 7, titre: "Relecture du numéro", etat: "en_cours", jetons: 12000, cout: 0.42, jauge: 0.35, changements: 0, genre: "principal", auteur: null, ...plus }) as never;

const monter = (f: ReturnType<typeof fil>, rappels: { arreter?: () => void; reprendre?: () => void; enCours?: boolean; lectureSeule?: boolean } = {}) =>
    render(
        <FournisseurLangue>
            <ShellStudio>
                <BandeauDuFil fil={f} enCours={rappels.enCours ?? true} lectureSeule={rappels.lectureSeule ?? false} arreter={rappels.arreter ?? vi.fn()} reprendre={rappels.reprendre ?? vi.fn()} />
                <p>le fil</p>
            </ShellStudio>
        </FournisseurLangue>,
    );

const barre = () => document.querySelector("[data-barre-actions]") as HTMLElement;

describe("bandeau du chat", () => {
    it("pose le titre en dernier maillon du fil d'Ariane, et l'état, la jauge, Arrêter et Ouvrir l'agent à droite", async () => {
        const arreter = vi.fn();
        monter(fil(), { arreter });
        const chemin = await screen.findByRole("navigation", { name: /Fil d'Ariane|Breadcrumb/ });
        expect(within(chemin).getByText("Relecture du numéro")).toBeTruthy();
        expect(within(chemin).getByText("Chat").closest("a")?.getAttribute("href")).toBe("/labo/builder");
        const droite = within(barre());
        expect(droite.getByText(/Au travail|Working/)).toBeTruthy();
        expect(droite.getByRole("button", { name: /Contexte 35 %|Context 35 %/ })).toBeTruthy();
        expect(droite.getByText(/Ouvrir l'agent|Open the agent/).closest("a")?.getAttribute("href")).toBe("/agents/7");
        fireEvent.click(droite.getByRole("button", { name: /Arrêter|Stop/ }));
        expect(arreter).toHaveBeenCalledTimes(1);
    });

    it("propose « Reprendre » à une conversation arrêtée, et pas « Arrêter »", async () => {
        const reprendre = vi.fn();
        monter(fil({ etat: "arretee" }), { reprendre, enCours: false });
        await screen.findByText("Relecture du numéro");
        expect(within(barre()).queryByRole("button", { name: /Arrêter|Stop/ })).toBeNull();
        fireEvent.click(within(barre()).getByRole("button", { name: /Reprendre|Resume/ }));
        expect(reprendre).toHaveBeenCalledTimes(1);
    });

    it("n'offre ni Arrêter ni Reprendre en lecture seule, ni « Ouvrir l'agent » sans agent", async () => {
        monter(fil({ workflow_id: null }), { lectureSeule: true });
        await screen.findByText("Relecture du numéro");
        expect(within(barre()).queryByRole("button", { name: /Arrêter|Stop|Reprendre|Resume/ })).toBeNull();
        expect(within(barre()).queryByText(/Ouvrir l'agent|Open the agent/)).toBeNull();
    });

    it("une conversation Claude Code montre sa marque et « En direct », sans boutons de pilotage ni jauge", async () => {
        monter(fil({ genre: "claude_code", auteur: "Evan", etat: "en_cours" }));
        await screen.findByText("Relecture du numéro");
        expect(within(barre()).getByText(/Claude Code/)).toBeTruthy();
        expect(within(barre()).getByText(/En direct|Live/)).toBeTruthy();
        expect(within(barre()).queryByRole("button", { name: /Arrêter|Stop|Contexte|Context/ })).toBeNull();
    });
});
