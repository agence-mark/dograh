/**
 * [.mark] C6: the required record fields of a pathway (chantier correctifs-banc-34).
 *
 * What these tests hold: the fields are the agent's own record fields, in a
 * drop-down (never one long block); ticking and unticking gives the list that
 * leaves in the save, and an empty choice leaves NOTHING (no check, as before);
 * a switched-off record says nothing is checked; a field gone from the record
 * is named. That the pathway dialog carries the component is asserted on the
 * dialog's own source below, and that the server reads the key is asserted on
 * the API schema.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChampsRequisSortie } from "./ChampsRequisSortie";

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

afterEach(cleanup);

const CHAMPS = ["nom", "numero_dicte", "commune", "adresse_intervention"];

describe("[.mark] required record fields of a pathway (C6)", () => {
    it("offers the record's fields in a drop-down and returns the ticked ones", () => {
        const onChange = vi.fn();
        render(<ChampsRequisSortie valeur={undefined} onChange={onChange} champs={CHAMPS} ficheAllumee />);
        const bouton = screen.getByRole("button", { name: /required record fields/i });
        expect(bouton.textContent).toContain("None");
        expect(document.getElementById("champ_requis_nom")).toBeNull();
        fireEvent.click(bouton);
        fireEvent.click(document.getElementById("champ_requis_commune") as HTMLElement);
        expect(onChange).toHaveBeenLastCalledWith(["commune"]);
    });

    it("unticking the last field leaves nothing (no check), never an empty list", () => {
        const onChange = vi.fn();
        render(<ChampsRequisSortie valeur={["nom"]} onChange={onChange} champs={CHAMPS} ficheAllumee />);
        fireEvent.click(screen.getByRole("button", { name: /required record fields/i }));
        fireEvent.click(document.getElementById("champ_requis_nom") as HTMLElement);
        expect(onChange).toHaveBeenLastCalledWith(undefined);
    });

    it("says nothing is checked when the record is switched off", () => {
        render(<ChampsRequisSortie valeur={["nom"]} onChange={vi.fn()} champs={CHAMPS} ficheAllumee={false} />);
        expect(document.querySelector('[data-note="fiche-eteinte"]')).not.toBeNull();
    });

    it("names a required field that is not in the record any more", () => {
        render(<ChampsRequisSortie valeur={["ancien_champ"]} onChange={vi.fn()} champs={CHAMPS} ficheAllumee />);
        expect(document.querySelector('[data-note="champs-disparus"]')?.textContent).toContain("ancien_champ");
    });

    it("the pathway dialog carries it, and saves the key the server reads", () => {
        const dialogue = readFileSync(join(__dirname, "../flow/edges/CustomEdge.tsx"), "utf8");
        expect(dialogue).toContain("<ChampsRequisSortie");
        expect(dialogue).toContain("champs_requis: champsRequis");
        const schema = readFileSync(join(__dirname, "../../../../api/services/workflow/dto.py"), "utf8");
        expect(schema).toContain("champs_requis: Optional[List[str]] = None");
    });
});
