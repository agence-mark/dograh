"use client";

import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef } from "react";

/**
 * Le standard des tableaux (E28, E34, E53) : sans cadre ni fond d'en-tête, en-têtes en petit gris, un trait entre
 * les lignes, des colonnes en texte, un point d'état pour un état, une pastille rouge seulement quand il faut agir.
 * Un clic sur la ligne ouvre l'objet ; les gestes rares vont dans l'objet ou dans un menu « … ».
 */
export type Colonne = {
    titre: React.ReactNode;
    droite?: boolean;
    largeur?: string;
    /**
     * Rang de repli (clôture D2) : quand la place manque (panneau de droite ouvert), le tableau masque ses colonnes les moins
     * utiles, la plus petite valeur d'abord, jusqu'à ce que tout tienne. Une colonne sans rang ne se masque jamais ; si ça ne
     * tient toujours pas, le tableau défile en lui-même (jamais la page de côté, jamais une colonne coupée à moitié).
     */
    secondaire?: number;
};

/** Montre ou masque (display none) la colonne `i` du tableau : en-tête et cellules. */
const colonneVisible = (table: HTMLTableElement, i: number, visible: boolean) => {
    for (const ligne of Array.from(table.rows)) {
        const cellule = ligne.cells[i] as HTMLTableCellElement | undefined;
        if (cellule && cellule.colSpan <= 1) cellule.style.display = visible ? "" : "none";
    }
};

export function Tableau({ colonnes, children }: { colonnes: Colonne[]; children: React.ReactNode }) {
    const boite = useRef<HTMLDivElement>(null);
    const table = useRef<HTMLTableElement>(null);
    const ajuster = () => {
        const b = boite.current;
        const t = table.current;
        if (!b || !t || b.clientWidth === 0) return;
        const ordre = colonnes
            .map((c, i) => ({ i, rang: c.secondaire }))
            .filter((x): x is { i: number; rang: number } => x.rang !== undefined)
            .sort((a, c) => a.rang - c.rang);
        for (const { i } of ordre) colonneVisible(t, i, true);
        for (const { i } of ordre) {
            if (t.scrollWidth <= b.clientWidth) break;
            colonneVisible(t, i, false);
        }
    };
    // À chaque rendu (une page de lignes change) et à chaque changement de largeur de la place offerte.
    useLayoutEffect(ajuster);
    useEffect(() => {
        const b = boite.current;
        if (!b || typeof ResizeObserver === "undefined") return;
        const observateur = new ResizeObserver(() => ajuster());
        observateur.observe(b);
        return () => observateur.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
        <div ref={boite} data-tableau className="w-full overflow-x-auto">
            <table ref={table} className="w-full text-sm">
                <thead className="border-b text-xs whitespace-nowrap text-muted-foreground">
                    <tr>
                        {colonnes.map((c, i) => (
                            <th
                                key={i}
                                className={`py-2 font-normal ${c.droite ? "text-right" : "text-left"} ${i > 0 ? "pl-4" : ""} ${c.largeur ?? ""}`}
                            >
                                {c.titre}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y">{children}</tbody>
            </table>
        </div>
    );
}

/**
 * Une ligne de tableau. [.mark] K4 : le routeur n'est lu que par une ligne qui mène à une adresse (`href`) ; une ligne qui
 * ouvre une fenêtre (`onClick`) n'en a pas besoin, et se rend donc aussi hors de l'application (tests, fenêtres).
 */
function LigneLien({ href, children }: { href: string; children: React.ReactNode }) {
    const router = useRouter();
    return (
        <tr onClick={() => router.push(href)} className="cursor-pointer hover:bg-muted/40 hover:font-medium">
            {children}
        </tr>
    );
}

export function Ligne({ href, onClick, children }: { href?: string; onClick?: () => void; children: React.ReactNode }) {
    if (href) return <LigneLien href={href}>{children}</LigneLien>;
    return (
        <tr onClick={onClick} className={onClick ? "cursor-pointer hover:bg-muted/40 hover:font-medium" : ""}>
            {children}
        </tr>
    );
}

/** Cellule : la première porte le nom (et une ligne grise facultative), les suivantes sont en gris. */
export function Cellule({
    children,
    sous,
    droite,
    principale,
    className = "",
}: {
    children: React.ReactNode;
    sous?: React.ReactNode;
    droite?: boolean;
    principale?: boolean;
    className?: string;
}) {
    return (
        <td className={`${principale ? "py-3" : "pl-4 text-muted-foreground"} ${droite ? "text-right tabular-nums" : ""} ${className}`}>
            {principale ? <span className="font-medium">{children}</span> : children}
            {sous && <span className="block text-xs text-muted-foreground">{sous}</span>}
        </td>
    );
}

/**
 * Le titre d'un tableau (E34, E53) : jamais de carte ni de cadre autour d'un tableau. Le titre et son « ! » à
 * gauche, l'action à droite, le tableau juste dessous.
 */
export function TitreTableau({ titre, info, action }: { titre: React.ReactNode; info?: React.ReactNode; action?: React.ReactNode }) {
    return (
        <div className="flex items-center gap-2 pt-4">
            <p className="flex flex-1 items-center gap-1.5 text-base font-semibold">
                {titre}
                {info}
            </p>
            {action}
        </div>
    );
}
