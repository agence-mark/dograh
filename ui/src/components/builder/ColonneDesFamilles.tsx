"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): the column of the Library. « New family » on top, then the families by group
 * (what builds the agent, what makes it work, ...), and under the chosen family its sub-folders (created here, removed
 * when empty). The sheet of a family (what it is, when to use it, how to write an element) sits in its « ! ».
 */
import { FolderPlus, Plus, X } from "lucide-react";
import { useState } from "react";

import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Input } from "@/components/ui/input";

import { GROUPES } from "./libelles";

interface Props {
    familles: VueFamille[];
    famille: string;
    dossier: string | null;
    dossiers: string[];
    onFamille: (slug: string) => void;
    onDossier: (chemin: string | null) => void;
    onNouvelleFamille: () => void;
    onNouveauDossier: (chemin: string) => void;
    onSupprimerDossier: (chemin: string) => void;
    onFiche: (slug: string) => void;
}

const BOUTON = "flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:font-medium";

export function ColonneDesFamilles(p: Props) {
    const { t } = useLangue();
    const [nouveau, setNouveau] = useState<string | null>(null);
    const groupes = [...new Set(p.familles.map((f) => f.groupe))];
    const choisie = p.familles.find((f) => f.slug === p.famille);

    const creer = () => {
        const chemin = (nouveau ?? "").trim().toLowerCase().replace(/\s+/g, "-");
        if (chemin) p.onNouveauDossier(p.dossier ? `${p.dossier}/${chemin}` : chemin);
        setNouveau(null);
    };

    return (
        <nav aria-label={t({ en: "Families", fr: "Familles" })} className="space-y-4 text-sm" data-testid="colonne-familles">
            <button type="button" className={`${BOUTON} font-medium text-(--acc)`} onClick={p.onNouvelleFamille}>
                <Plus className="size-4" /> {t({ en: "New family", fr: "Nouvelle famille" })}
            </button>
            <button
                type="button"
                className={`${BOUTON} ${p.famille === "" ? "bg-muted font-medium" : ""}`}
                aria-current={p.famille === ""}
                onClick={() => p.onFamille("")}
            >
                {t({ en: "All families", fr: "Toutes les familles" })}
            </button>
            {groupes.map((g) => (
                <div key={g} className="space-y-0.5">
                    <p className="px-2 pb-1 text-xs text-muted-foreground">{GROUPES[g] ? t(GROUPES[g]) : g}</p>
                    {p.familles
                        .filter((f) => f.groupe === g)
                        .map((f) => (
                            <div key={f.slug}>
                                <div className="flex items-center">
                                    <button
                                        type="button"
                                        className={`${BOUTON} ${p.famille === f.slug ? "bg-muted font-medium" : ""}`}
                                        aria-current={p.famille === f.slug}
                                        data-testid={`famille-${f.slug}`}
                                        onClick={() => p.onFamille(f.slug)}
                                    >
                                        {f.libelle}
                                    </button>
                                    {p.famille === f.slug && (
                                        <button type="button" className="shrink-0 px-1" onClick={() => p.onFiche(f.slug)} aria-label={t({ en: "Sheet of the family", fr: "Fiche de la famille" })} title={t({ en: "Sheet of the family", fr: "Fiche de la famille" })}>
                                            <Info>{[f.fiche?.description, f.fiche?.quand].filter(Boolean).join(" ")}</Info>
                                        </button>
                                    )}
                                </div>
                                {p.famille === f.slug && (
                                    <div className="ml-3 space-y-0.5 border-l pl-2" data-testid="sous-dossiers">
                                        {p.dossiers.map((d) => (
                                            <div key={d} className="flex items-center" style={{ paddingLeft: `${(d.split("/").length - 1) * 0.75}rem` }}>
                                                <button
                                                    type="button"
                                                    className={`${BOUTON} ${p.dossier === d ? "bg-muted font-medium" : ""}`}
                                                    onClick={() => p.onDossier(p.dossier === d ? null : d)}
                                                >
                                                    {d.split("/").pop()}
                                                </button>
                                                <button
                                                    type="button"
                                                    className="shrink-0 cursor-pointer px-1 text-muted-foreground hover:text-foreground"
                                                    aria-label={t({ en: `Remove the folder ${d}`, fr: `Supprimer le sous-dossier ${d}` })}
                                                    onClick={() => p.onSupprimerDossier(d)}
                                                >
                                                    <X className="size-3" />
                                                </button>
                                            </div>
                                        ))}
                                        {nouveau === null ? (
                                            <button type="button" className={`${BOUTON} text-muted-foreground`} onClick={() => setNouveau("")}>
                                                <FolderPlus className="size-4" /> {t({ en: "Sub-folder", fr: "Sous-dossier" })}
                                            </button>
                                        ) : (
                                            <Input
                                                autoFocus
                                                value={nouveau}
                                                placeholder={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                                                aria-label={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                                                className="h-7"
                                                onChange={(e) => setNouveau(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === "Enter") creer();
                                                    if (e.key === "Escape") setNouveau(null);
                                                }}
                                                onBlur={creer}
                                            />
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                </div>
            ))}
            {choisie && <span className="sr-only">{choisie.libelle}</span>}
        </nav>
    );
}
