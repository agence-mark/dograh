"use client";

/**
 * [.mark] Une erreur de saisie se lit SOUS le champ, jamais dans une notification (`15-notifications.md`, règle 5).
 * Rend rien quand il n'y a pas de faute. Le champ porte `aria-invalid` et `aria-describedby={id}`.
 */
export function ErreurChamp({ id, children }: { id?: string; children?: React.ReactNode }) {
    if (!children) return null;
    return (
        <p id={id} role="alert" className="text-sm text-(--marque-danger-texte)">
            {children}
        </p>
    );
}
