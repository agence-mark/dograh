/**
 * [.mark] U3 quater (E65) : l'onglet « Site » d'un agent.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | visibilité | l'onglet n'existe que pour un agent dont le canal est le site |
 * | adresse | `/agents/<id>/site` est l'onglet Site |
 * | résumé | le site, ses pages, le script détecté et l'état viennent du serveur |
 * | même éditeur | « Configurer le module » monte `EditeurWidget`, l'éditeur de la maquette, le même que celui de l'écran « Intégrer » |
 * | téléphone | un agent téléphonique ne montre rien à configurer |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({ emplacement: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), { lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet: sdk.emplacement }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => <a href={href} {...rest}>{children}</a> }));
vi.mock("../agent/MenuMembre", () => ({ MenuMembre: () => null }));
vi.mock("./EditeurWidget", () => ({ EditeurWidget: ({ workflowId }: { workflowId: number }) => <div data-testid="editeur-widget">{workflowId}</div> }));

import { adresseOnglet, ongletDeAdresse } from "../agent/onglets-agent";
import { OngletsAgent } from "../agent/OngletsAgent";
import { PageSiteAgent } from "./PageSiteAgent";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const SITE = { workflow_id: 7, canal: "site", site_cle: "site_abc", chemins: ["/", "/contact"], widget_actif: true, dernier_chargement: "2026-11-02" };

describe("l'onglet Site", () => {
    it("n'apparaît que si le canal de l'agent est le site", async () => {
        sdk.emplacement.mockResolvedValue({ data: { ...SITE, canal: "telephone" } });
        const { unmount } = render(<FournisseurLangue><OngletsAgent agentId={7} actif="parcours" /></FournisseurLangue>);
        await waitFor(() => expect(sdk.emplacement).toHaveBeenCalled());
        expect(document.querySelector('[data-onglet="site"]')).toBeNull();
        unmount();
        sdk.emplacement.mockResolvedValue({ data: SITE });
        render(<FournisseurLangue><OngletsAgent agentId={7} actif="site" /></FournisseurLangue>);
        await waitFor(() => expect(document.querySelector('[data-onglet="site"]')).not.toBeNull());
        expect(document.querySelector('[data-onglet="site"]')?.getAttribute("href")).toBe("/agents/7/site");
    });

    it("a son adresse", () => {
        expect(adresseOnglet(7, "site")).toBe("/agents/7/site");
        expect(ongletDeAdresse("/agents/7/site")).toBe("site");
        expect(ongletDeAdresse("/agents/7/tests")).toBe("tests");
    });

    it("résume le module et ouvre le même éditeur que l'écran Intégrer", async () => {
        sdk.emplacement.mockResolvedValue({ data: SITE });
        render(<FournisseurLangue><PageSiteAgent agentId={7} /></FournisseurLangue>);
        expect((await screen.findByText("site_abc")).textContent).toBe("site_abc");
        expect(document.querySelector("[data-chemins]")?.textContent).toBe("/, /contact");
        expect(document.querySelector("[data-etat]")?.textContent).toMatch(/Actif|Active/);
        expect(screen.queryByTestId("editeur-widget")).toBeNull();
        fireEvent.click(screen.getByTestId("configurer-module"));
        expect(screen.getByTestId("editeur-widget").textContent).toBe("7");
    });

    it("ne propose rien à configurer pour un agent téléphonique", async () => {
        sdk.emplacement.mockResolvedValue({ data: { ...SITE, canal: "telephone" } });
        render(<FournisseurLangue><PageSiteAgent agentId={7} /></FournisseurLangue>);
        expect(await screen.findByTestId("site-pas-le-canal")).not.toBeNull();
        expect(screen.queryByTestId("configurer-module")).toBeNull();
    });
});
