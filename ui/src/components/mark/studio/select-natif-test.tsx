/**
 * [.mark] V1b : un `<select>` du navigateur qui tient la place du `Select` du design system, DANS LES TESTS SEULEMENT.
 *
 * Le `Select` (Radix) ne s'ouvre pas sous JSDOM sans artifices de pointeur. Les écrans passent par `ListeDeroulante`
 * (le `Select` du design system) ; un test qui choisit une valeur (`fireEvent.change`, `selectOptions`) remplace
 * `@/components/ui/select` par ce module : le déclencheur donne son `id`, ses `aria-*` et ses `data-*` au `<select>`,
 * les options deviennent des `<option>`. Ce que le test prouve reste ce que l'écran envoie une fois la valeur choisie.
 *
 *     vi.mock("@/components/ui/select", async () => await import("@/components/mark/studio/select-natif-test"));
 */
import { createContext, type ReactNode, useContext } from "react";

interface Etat {
    value?: string;
    onValueChange?: (valeur: string) => void;
    disabled?: boolean;
    name?: string;
    // Posé par le déclencheur pendant le rendu : il passe avant le contenu (frères, dans l'ordre).
    attributs: Record<string, unknown>;
}

const Contexte = createContext<Etat>({ attributs: {} });

export const Select = ({
    value,
    defaultValue,
    onValueChange,
    disabled,
    name,
    children,
}: {
    value?: string;
    defaultValue?: string;
    onValueChange?: (valeur: string) => void;
    disabled?: boolean;
    name?: string;
    required?: boolean;
    children?: ReactNode;
}) => {
    const etat: Etat = { value: value ?? defaultValue, onValueChange, disabled, name, attributs: {} };
    return <Contexte.Provider value={etat}>{children}</Contexte.Provider>;
};

export const SelectTrigger = ({ id, className: _classe, size: _taille, children: _enfants, ...attributs }: Record<string, unknown> & { id?: string; children?: ReactNode }) => {
    const etat = useContext(Contexte);
    etat.attributs = { id, ...attributs };
    return null;
};

export const SelectValue = () => null;

export const SelectContent = ({ children }: { children?: ReactNode }) => {
    const etat = useContext(Contexte);
    const { onKeyDown, autoFocus, title, ...autres } = etat.attributs as Record<string, unknown>;
    return (
        <select
            {...(autres as Record<string, string>)}
            title={title as string | undefined}
            name={etat.name}
            value={etat.value ?? ""}
            disabled={etat.disabled}
            onKeyDown={onKeyDown as never}
            autoFocus={autoFocus as boolean | undefined}
            onChange={(e) => etat.onValueChange?.(e.target.value)}
        >
            {(etat.value === undefined || etat.value === "") && <option value="" />}
            {children}
        </select>
    );
};

export const SelectItem = ({ value, disabled, children }: { value: string; disabled?: boolean; children?: ReactNode }) => (
    <option value={value} disabled={disabled}>
        {typeof children === "string" || typeof children === "number" ? children : value}
    </option>
);

export const SelectGroup = ({ children }: { children?: ReactNode }) => <>{children}</>;
export const SelectLabel = () => null;
export const SelectSeparator = () => null;
export const SelectScrollUpButton = () => null;
export const SelectScrollDownButton = () => null;
