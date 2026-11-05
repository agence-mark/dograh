"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";

import { useLangue } from "../langue/langue";

/**
 * Lignes éditables (en-têtes, paramètres, copies vers la fiche, réponses simulées) : un tableau nu, une ligne de
 * saisie par entrée, jamais de carte (E34). `rendu` rend les cellules d'une ligne.
 */
export function LignesEditables<T>({
    colonnes,
    lignes,
    changer,
    vide,
    nouvelle,
    ajouter,
    rendu,
}: {
    colonnes: string[];
    lignes: T[];
    changer: (l: T[]) => void;
    vide: string;
    nouvelle: () => T;
    ajouter: string;
    rendu: (ligne: T, maj: (p: Partial<T>) => void, index: number) => React.ReactNode[];
}) {
    const { t } = useLangue();
    // Une identité par ligne : retirer une ligne plus haut garde les autres (et le focus) où ils sont.
    const identites = useRef<number[]>([]);
    const suivante = useRef(0);
    while (identites.current.length < lignes.length) identites.current.push(suivante.current++);
    if (identites.current.length > lignes.length) identites.current.length = lignes.length;
    return (
        <div>
            {lignes.length > 0 ? (
                <table className="w-full text-sm">
                    <thead className="border-b text-xs text-muted-foreground">
                        <tr>
                            {colonnes.map((c, i) => (
                                <th key={c} className={`py-2 text-left font-normal ${i ? "pl-3" : ""}`}>
                                    {c}
                                </th>
                            ))}
                            <th className="w-8" />
                        </tr>
                    </thead>
                    <tbody className="divide-y">
                        {lignes.map((l, i) => {
                            const maj = (p: Partial<T>) => changer(lignes.map((x, j) => (j === i ? { ...x, ...p } : x)));
                            return (
                                <tr key={identites.current[i]}>
                                    {rendu(l, maj, i).map((cellule, k) => (
                                        <td key={k} className={`py-2 ${k ? "pl-3" : ""}`}>
                                            {cellule}
                                        </td>
                                    ))}
                                    <td className="pl-2 text-right">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                identites.current.splice(i, 1);
                                                changer(lignes.filter((_, j) => j !== i));
                                            }}
                                            className="cursor-pointer text-muted-foreground hover:text-foreground"
                                            aria-label={t({ en: "Remove", fr: "Retirer" })}
                                        >
                                            <Trash2 className="size-4" />
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            ) : (
                <p className="py-1 text-sm text-muted-foreground">{vide}</p>
            )}
            <Button variant="ghost" size="sm" className="-ml-2 mt-1" onClick={() => changer([...lignes, nouvelle()])}>
                <Plus className="size-4" /> {ajouter}
            </Button>
        </div>
    );
}
