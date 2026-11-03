"use client";

import { useRouter } from "next/navigation";

/**
 * Le standard des tableaux (E28, E34, E53) : sans cadre ni fond d'en-tête, en-têtes en petit gris, un trait entre
 * les lignes, des colonnes en texte, un point d'état pour un état, une pastille rouge seulement quand il faut agir.
 * Un clic sur la ligne ouvre l'objet ; les gestes rares vont dans l'objet ou dans un menu « … ».
 */
export type Colonne = { titre: React.ReactNode; droite?: boolean; largeur?: string };

export function Tableau({ colonnes, children }: { colonnes: Colonne[]; children: React.ReactNode }) {
    return (
        <table className="w-full text-sm">
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
