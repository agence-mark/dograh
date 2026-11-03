"use client";

import { Plus, Trash2 } from "lucide-react";

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
                                <tr key={i}>
                                    {rendu(l, maj, i).map((cellule, k) => (
                                        <td key={k} className={`py-2 ${k ? "pl-3" : ""}`}>
                                            {cellule}
                                        </td>
                                    ))}
                                    <td className="pl-2 text-right">
                                        <button
                                            type="button"
                                            onClick={() => changer(lignes.filter((_, j) => j !== i))}
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
