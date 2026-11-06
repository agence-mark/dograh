/**
 * [.mark] V1b : un `<select>` du navigateur qui tient la place de `ListeDeroulante`, DANS LES TESTS SEULEMENT.
 *
 * Les écrans passent par `ListeDeroulante` (le `Select` du design system, Radix), qui ne s'ouvre pas sous JSDOM sans
 * artifices de pointeur. Un test qui choisit une valeur (`fireEvent.change`, `selectOptions`) ou lit les options
 * remplace le module par celui-ci : l'écran envoie ce qu'il envoie une fois la valeur choisie, c'est cela que le test
 * prouve. Le vrai composant a son propre test (`liste-deroulante.test.tsx`).
 *
 *     vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
 */
import type { ReactNode } from "react";

import type { PropsListeDeroulante } from "./liste-deroulante";

export function ListeDeroulante({ onChange, children, value, ...reste }: PropsListeDeroulante & { children?: ReactNode }) {
    // Le texte d'attente (`placeholder`) n'existe pas sur un <select> : il ne passe pas.
    delete reste.placeholder;
    return (
        <select
            {...(reste as Record<string, unknown>)}
            value={value as string | number | undefined}
            onChange={(e) => onChange?.({ target: { value: e.target.value }, currentTarget: { value: e.target.value } })}
        >
            {children}
        </select>
    );
}
