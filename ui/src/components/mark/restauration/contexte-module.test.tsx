/**
 * [.mark] Lot 26, M50 : « Ajouter un module » ne dit jamais « ajouté » si le serveur ne l'a pas pris (l'état relu fait foi).
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurModuleRestauration, useModuleRestauration } from "./contexte";

const poserLeModule = vi.fn();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("./donnees", () => ({
    lireLeModule: async () => ({ data: { actif: false, etablissements: [] }, error: undefined }),
    poserLeModule: (v: boolean) => poserLeModule(v),
}));
const echec = vi.fn();
vi.mock("../notifications", () => ({ notifier: { echec: (...a: unknown[]) => echec(...a), succes: vi.fn() } }));
vi.mock("../notifications/echec-affiche", () => ({ echecAffiche: vi.fn() }));

let valeur: ReturnType<typeof useModuleRestauration>;
function Sonde() {
    valeur = useModuleRestauration();
    return null;
}

describe("M50 : l'état rendu par le serveur fait foi", () => {
    afterEach(() => { cleanup(); poserLeModule.mockReset(); echec.mockReset(); });
    it("le serveur rend « actif » : poser réussit", async () => {
        poserLeModule.mockResolvedValue({ data: { actif: true, etablissements: [] }, error: undefined });
        render(<FournisseurModuleRestauration><Sonde /></FournisseurModuleRestauration>);
        let pris = false;
        await act(async () => { pris = await valeur.poser(true); });
        expect(pris).toBe(true);
        expect(valeur.actif).toBe(true);
        expect(echec).not.toHaveBeenCalled();
    });
    it("le serveur rend l'état d'avant : poser échoue et le dit, rien n'est « ajouté »", async () => {
        poserLeModule.mockResolvedValue({ data: { actif: false, etablissements: [] }, error: undefined });
        render(<FournisseurModuleRestauration><Sonde /></FournisseurModuleRestauration>);
        let pris = true;
        await act(async () => { pris = await valeur.poser(true); });
        expect(pris).toBe(false);
        expect(valeur.actif).toBe(false);
        expect(echec).toHaveBeenCalledTimes(1);
    });
});
