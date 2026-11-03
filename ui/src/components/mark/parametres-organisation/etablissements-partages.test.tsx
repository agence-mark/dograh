/**
 * [.mark] C4 : les établissements sont lus UNE fois par page (Entreprise les lisait quatre fois) ; sans fournisseur, chaque
 * consommateur lit pour son compte (les autres écrans ne changent pas) ; une relecture sur demande met tout le monde à jour.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ lire: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ getEtablissementsApiV1OrganizationsEtablissementsGet: m.lire }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

import { FournisseurEtablissements, useEtablissementsPartages, useLireEtablissements } from "./etablissements-partages";

function Lecteur({ nom }: { nom: string }) {
    const partage = useEtablissementsPartages();
    const propre = useLireEtablissements(partage === null);
    const { liste } = partage ?? propre;
    return <span data-testid={nom}>{liste === null ? "…" : liste.map((e) => e.nom).join(",")}</span>;
}

let relireDehors: (() => Promise<void>) | null = null;
function Relance() {
    const partage = useEtablissementsPartages();
    relireDehors = partage?.relire ?? null;
    return null;
}

beforeEach(() => {
    m.lire.mockReset();
    m.lire.mockResolvedValue({ data: { etablissements: [{ id: "a", nom: "Beauvais" }] } });
});
afterEach(() => cleanup());

describe("[.mark] C4 : une lecture des établissements par page", () => {
    it("quatre lecteurs sous un fournisseur = une seule requête", async () => {
        render(
            <FournisseurEtablissements>
                {["un", "deux", "trois", "quatre"].map((n) => <Lecteur key={n} nom={n} />)}
            </FournisseurEtablissements>,
        );
        await waitFor(() => expect(screen.getByTestId("quatre").textContent).toBe("Beauvais"));
        expect(m.lire).toHaveBeenCalledTimes(1);
    });

    it("sans fournisseur, chaque lecteur lit pour son compte", async () => {
        render(<><Lecteur nom="un" /><Lecteur nom="deux" /></>);
        await waitFor(() => expect(screen.getByTestId("deux").textContent).toBe("Beauvais"));
        expect(m.lire).toHaveBeenCalledTimes(2);
    });

    it("une relecture sur demande (après une écriture) met tous les lecteurs à jour", async () => {
        render(
            <FournisseurEtablissements>
                <Relance />
                <Lecteur nom="un" />
                <Lecteur nom="deux" />
            </FournisseurEtablissements>,
        );
        await waitFor(() => expect(screen.getByTestId("un").textContent).toBe("Beauvais"));
        m.lire.mockResolvedValue({ data: { etablissements: [{ id: "a", nom: "Beauvais" }, { id: "b", nom: "Creil" }] } });
        await act(async () => { await relireDehors?.(); });
        expect(screen.getByTestId("un").textContent).toBe("Beauvais,Creil");
        expect(screen.getByTestId("deux").textContent).toBe("Beauvais,Creil");
        expect(m.lire).toHaveBeenCalledTimes(2);
    });
});
