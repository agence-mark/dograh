"use client";

/**
 * [.mark] K4b : les puces de la maquette (`OngletVerification`) : un choix multiple en pastilles, actives en plein.
 * Même geste que le type `multi` de `FenetreChamps` ; ici une pastille garde un identifiant (case de test) et un libellé.
 */
export type PuceChoix = { cle: string; libelle: string };

export function Puces({
    choix,
    valeur,
    changer,
    testid,
}: {
    choix: PuceChoix[];
    valeur: string[];
    changer: (v: string[]) => void;
    testid?: (cle: string) => string;
}) {
    return (
        <div className="flex flex-wrap gap-1.5">
            {choix.map((c) => {
                const actif = valeur.includes(c.cle);
                return (
                    <button
                        key={c.cle}
                        type="button"
                        aria-pressed={actif}
                        data-testid={testid?.(c.cle)}
                        onClick={() => changer(actif ? valeur.filter((x) => x !== c.cle) : [...valeur, c.cle])}
                        className={`cursor-pointer rounded-full border px-2.5 py-1 text-xs ${actif ? "border-foreground bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:font-medium"}`}
                    >
                        {c.libelle}
                    </button>
                );
            })}
        </div>
    );
}
