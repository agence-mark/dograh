/**
 * [.mark] A native <select> standing in for the Radix Select, TESTS ONLY.
 *
 * The Radix Select cannot be driven in JSDOM without pointer-capture polyfills
 * and portal timing. The payload references do not test the Select: they test
 * what a card sends once a value is chosen. So every reference test mocks
 * `@/components/ui/select` with this module, and the OLD cards (step 1) and the
 * NEW themes (step 4) are driven through the very same control: a difference
 * in the payload can then only come from the screen, never from the harness.
 *
 * The trigger's `id` becomes the native select's `id`, so a test chooses a
 * value with `fireEvent.change(document.getElementById(id), …)`.
 */
import { createContext, type ReactNode, useContext } from "react";

interface Etat {
    value?: string;
    onValueChange?: (valeur: string) => void;
    disabled?: boolean;
    // Mutated by the trigger during render: the trigger renders before the
    // content (siblings, in order), so the content reads the id it set.
    id?: string;
}

const Contexte = createContext<Etat>({});

export const Select = ({
    value,
    onValueChange,
    disabled,
    children,
}: {
    value?: string;
    onValueChange?: (valeur: string) => void;
    disabled?: boolean;
    children?: ReactNode;
}) => {
    const etat: Etat = { value, onValueChange, disabled };
    return <Contexte.Provider value={etat}>{children}</Contexte.Provider>;
};

export const SelectTrigger = ({ id }: { id?: string; children?: ReactNode; className?: string }) => {
    const etat = useContext(Contexte);
    etat.id = id;
    return null;
};

export const SelectValue = () => null;

export const SelectContent = ({ children }: { children?: ReactNode }) => {
    const etat = useContext(Contexte);
    return (
        <select
            id={etat.id}
            value={etat.value ?? ""}
            disabled={etat.disabled}
            onChange={(e) => etat.onValueChange?.(e.target.value)}
        >
            {etat.value === undefined && <option value="" />}
            {children}
        </select>
    );
};

export const SelectItem = ({ value, children }: { value: string; children?: ReactNode }) => (
    <option value={value}>{typeof children === "string" ? children : value}</option>
);

export const SelectGroup = ({ children }: { children?: ReactNode }) => <>{children}</>;
export const SelectLabel = () => null;
export const SelectSeparator = () => null;
export const SelectScrollUpButton = () => null;
export const SelectScrollDownButton = () => null;
