"use client";

/**
 * [.mark] K2b : des choix côte à côte, dans un cadre arrondi, le choix actif plein (maquette `Choix` de `modale-noeud.tsx`).
 * Pour quelques choix courts ; au-delà, une liste. Un seul est actif ; le survol met en gras, jamais en souligné.
 */
export function ChoixCoteACote<V extends string | number>({
    options,
    valeur,
    onChange,
    libelle,
    id,
}: {
    options: { value: V; label: string }[];
    valeur: V | undefined;
    onChange: (v: V) => void;
    /** Le libellé lu par les lecteurs d'écran. */
    libelle: string;
    id?: string;
}) {
    return (
        <div id={id} role="radiogroup" aria-label={libelle} className="inline-flex w-fit flex-wrap rounded-lg border p-0.5">
            {options.map((o) => (
                <button
                    key={String(o.value)}
                    type="button"
                    role="radio"
                    aria-checked={o.value === valeur}
                    onClick={() => onChange(o.value)}
                    className={`cursor-pointer rounded-md px-3 py-1 text-sm ${
                        o.value === valeur ? "bg-foreground text-background" : "text-muted-foreground hover:font-medium hover:text-foreground"
                    }`}
                >
                    {o.label}
                </button>
            ))}
        </div>
    );
}
