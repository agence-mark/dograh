"use client";

/**
 * [.mark] V1b : la liste déroulante du design system (le `Select` de la maquette) sous la forme d'un `<select>`.
 *
 * Evan (02/11) : une seule liste déroulante à l'écran, celle du design system, jamais celle du navigateur. Ce composant
 * remplace les `<select>` du fork SANS réécrire leurs appels : il prend les mêmes propriétés (`value`, `onChange`,
 * `disabled`, `id`, `aria-label`, `className`) et les mêmes `<option>` enfants, et dessine le `Select` de la maquette.
 * `onChange` reçoit `{ target: { value } }` comme avec le navigateur ; une option de valeur vide devient la sentinelle de
 * `Liste` (Radix refuse la valeur vide).
 *
 * La classe écrite pour le `<select>` du navigateur (bordure, fond, hauteur) est jetée : le déclencheur du design system
 * a sa propre forme. Seules les classes de placement (largeur, marge, flex, grille) sont gardées.
 */
import { Children, isValidElement, type KeyboardEventHandler, type ReactElement, type ReactNode } from "react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { VALEUR_VIDE } from "./liste";

type Option = { valeur: string; libelle: ReactNode; desactivee: boolean };

type PropsOption = { value?: string | number; disabled?: boolean; children?: ReactNode; hidden?: boolean };

/** Les `<option>` enfants, à plat (fragments traversés). Une option sans `value` vaut son texte, comme le navigateur. */
export function optionsDe(enfants: ReactNode): Option[] {
    const sortie: Option[] = [];
    Children.forEach(enfants, (enfant) => {
        if (!isValidElement(enfant)) return;
        const el = enfant as ReactElement<PropsOption & { children?: ReactNode }>;
        if (el.type === "option") {
            if (el.props.hidden) return;
            const texte = Children.toArray(el.props.children)
                .filter((x) => typeof x === "string" || typeof x === "number")
                .join("");
            sortie.push({
                valeur: el.props.value === undefined ? texte : String(el.props.value),
                libelle: el.props.children,
                desactivee: Boolean(el.props.disabled),
            });
            return;
        }
        // Un fragment (ou un tableau) d'options.
        sortie.push(...optionsDe(el.props.children));
    });
    return sortie;
}

const PLACEMENT = /^(w-|min-w-|max-w-|flex$|flex-|grow|shrink|basis-|self-|justify-self-|col-|row-|m[trblxy]?-|-m[trblxy]?-|order-|sm:w-|md:w-|lg:w-|sm:col-|md:col-)/;

/** Ne garde que les classes de placement de la classe écrite pour le `<select>` du navigateur. */
export function classesDePlacement(classe: string | undefined): string {
    return (classe ?? "")
        .split(/\s+/)
        .filter((c) => c && PLACEMENT.test(c))
        .join(" ");
}

export interface PropsListeDeroulante {
    value?: string | number | readonly string[];
    defaultValue?: string | number;
    onChange?: (e: { target: { value: string }; currentTarget: { value: string } }) => void;
    disabled?: boolean;
    id?: string;
    name?: string;
    className?: string;
    children?: ReactNode;
    title?: string;
    required?: boolean;
    autoFocus?: boolean;
    "aria-label"?: string;
    "aria-labelledby"?: string;
    "aria-invalid"?: boolean | "true" | "false";
    "data-testid"?: string;
    "data-case"?: string;
    onKeyDown?: KeyboardEventHandler<HTMLButtonElement>;
    /** Le texte montré quand rien n'est choisi. */
    placeholder?: string;
}

export function ListeDeroulante({
    value,
    defaultValue,
    onChange,
    disabled,
    id,
    name,
    className,
    children,
    placeholder,
    ...reste
}: PropsListeDeroulante) {
    const options = optionsDe(children);
    const valeur = value === undefined ? undefined : String(Array.isArray(value) ? value[0] ?? "" : value);
    const poser = (x: string) => {
        const choisie = x === VALEUR_VIDE ? "" : x;
        onChange?.({ target: { value: choisie }, currentTarget: { value: choisie } });
    };
    // Une valeur vide existe quand une option de valeur vide existe ; sinon « rien de choisi » montre le texte d'attente.
    const aVide = options.some((o) => o.valeur === "");
    const courante = valeur === undefined ? undefined : valeur === "" ? (aVide ? VALEUR_VIDE : "") : valeur;
    return (
        <Select
            value={courante}
            defaultValue={defaultValue === undefined ? undefined : String(defaultValue)}
            onValueChange={poser}
            disabled={disabled}
            name={name}
            required={reste.required}
        >
            <SelectTrigger
                id={id}
                size="default"
                className={cn("bg-background", classesDePlacement(className))}
                aria-label={reste["aria-label"]}
                aria-labelledby={reste["aria-labelledby"]}
                aria-invalid={reste["aria-invalid"]}
                title={reste.title}
                autoFocus={reste.autoFocus}
                onKeyDown={reste.onKeyDown}
                data-testid={reste["data-testid"]}
                data-case={reste["data-case"]}
            >
                <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
                {options.map((o) => (
                    <SelectItem key={o.valeur === "" ? VALEUR_VIDE : o.valeur} value={o.valeur === "" ? VALEUR_VIDE : o.valeur} disabled={o.desactivee}>
                        {o.libelle}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}
