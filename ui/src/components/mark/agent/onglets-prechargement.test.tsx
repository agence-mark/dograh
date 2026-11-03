/** [.mark] L : les onglets d'un agent sont des liens `next/link` préchargés en entier (la page s'ouvre sans attendre son code). */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { OngletsAgent } from "./OngletsAgent";

const liens = vi.hoisted(() => [] as { href: string; prefetch?: boolean }[]);
vi.mock("next/link", () => ({
    default: ({ href, prefetch, children, ...reste }: { href: string; prefetch?: boolean; children: React.ReactNode }) => {
        liens.push({ href, prefetch });
        return (
            <a href={href} {...reste}>
                {children}
            </a>
        );
    },
}));
vi.mock("../site/useAgentDeSite", () => ({ useAgentDeSite: () => false }));
afterEach(cleanup);

describe("onglets d'un agent", () => {
    it("chaque onglet est un lien préchargé", () => {
        render(
            <FournisseurLangue>
                <OngletsAgent agentId={7} actif="parcours" />
            </FournisseurLangue>,
        );
        expect(screen.getAllByRole("tab")).toHaveLength(5);
        expect(liens.map((l) => l.href)).toContain("/agents/7/tests");
        expect(liens.every((l) => l.prefetch === true)).toBe(true);
    });
});
