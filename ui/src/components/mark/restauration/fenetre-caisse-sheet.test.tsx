/**
 * [.mark] Lot 26, M20 : la fenêtre latérale d'essai (sous 1280 px) ne se ferme plus quand on clique dans la fenêtre Caisse
 * ou dans une de ses listes ; elle se ferme toujours pour un clic ailleurs.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

import { ignorerLaCaisse } from "./fenetre-caisse";

function Essai({ filtre }: { filtre: boolean }) {
    const [ouvert, setOuvert] = useState(true);
    return (
        <>
            <button type="button">hors-caisse</button>
            <section data-fenetre-caisse><button type="button">dans-caisse</button></section>
            <div data-radix-popper-content-wrapper><div role="listbox"><button type="button">dans-liste</button></div></div>
            <Sheet open={ouvert} onOpenChange={setOuvert} modal={false}>
                <SheetContent onInteractOutside={filtre ? ignorerLaCaisse : undefined}><SheetTitle>Essai</SheetTitle></SheetContent>
            </Sheet>
        </>
    );
}

const clic = async (nom: string) => {
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    fireEvent.pointerDown(screen.getByText(nom), { pointerType: "mouse", button: 0 });
    fireEvent.mouseDown(screen.getByText(nom));
    fireEvent.mouseUp(screen.getByText(nom));
    fireEvent.click(screen.getByText(nom));
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
};

describe("M20 : la fenêtre d'essai et la fenêtre Caisse", () => {
    afterEach(cleanup);
    it("sans le filtre, un clic dans la caisse ferme l'essai (le défaut)", async () => {
        render(<Essai filtre={false} />);
        await clic("dans-caisse");
        expect(screen.queryByText("Essai")).toBeNull();
    });
    it("avec le filtre, un clic dans la caisse ou dans sa liste garde l'essai ouvert", async () => {
        render(<Essai filtre />);
        await clic("dans-caisse");
        expect(screen.queryByText("Essai")).not.toBeNull();
        await clic("dans-liste");
        expect(screen.queryByText("Essai")).not.toBeNull();
    });
    it("avec le filtre, un clic ailleurs ferme toujours l'essai", async () => {
        render(<Essai filtre />);
        await clic("hors-caisse");
        expect(screen.queryByText("Essai")).toBeNull();
    });
});
