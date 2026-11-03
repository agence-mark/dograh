/**
 * [.mark] K8 : le constructeur de filtres n'est jamais dans une carte (E34) : une barre d'outils (critère à ajouter,
 * modèles), puis les critères actifs en lignes nues ; « Appliquer » reste là dès qu'un critère existe.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActiveFilter, FilterAttribute } from "@/types/filters";

import { FilterBuilder } from "./FilterBuilder";

const ATTRIBUTS: FilterAttribute[] = [
    { id: "callerNumber", type: "text", label: "Caller number", config: { placeholder: "+33" } },
    { id: "runId", type: "number", label: "Run ID", config: {} },
];

afterEach(() => cleanup());

describe("[.mark] K8 : filtres nus", () => {
    it("sans critère : la barre d'outils seule, aucune carte, pas de bouton « Appliquer »", () => {
        const { container } = render(
            <FilterBuilder availableAttributes={ATTRIBUTS} activeFilters={[]} onFiltersChange={vi.fn()} onApplyFilters={vi.fn()} />,
        );
        expect(container.querySelector('[data-slot="card"]')).toBeNull();
        expect(container.querySelector('[data-forme="filtres-nus"]')).not.toBeNull();
        expect(screen.getByRole("combobox")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Templates" })).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Apply/ })).toBeNull();
    });

    it("avec un critère : une ligne nue qui se déplie, « Appliquer » apparaît et agit", () => {
        const actif: ActiveFilter[] = [
            { attribute: ATTRIBUTS[0], value: { value: "" }, isValid: true } as unknown as ActiveFilter,
        ];
        const appliquer = vi.fn();
        const { container } = render(
            <FilterBuilder availableAttributes={ATTRIBUTS} activeFilters={actif} onFiltersChange={vi.fn()} onApplyFilters={appliquer} />,
        );
        expect(container.querySelector('[data-slot="card"]')).toBeNull();
        expect(screen.getByText("Caller number")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /Apply/ }));
        expect(appliquer).toHaveBeenCalledTimes(1);
    });
});
