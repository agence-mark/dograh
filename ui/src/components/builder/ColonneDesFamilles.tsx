"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): the column of the Library. « New family » on top, then the families by group
 * (what builds the agent, what makes it work, ...), and under the chosen family its sub-folders (created here, removed
 * when empty). The sheet of a family (what it is, when to use it, how to write an element) sits in its « ! ».
 */
import { BookOpen, Folder, FolderPlus, Plus, X } from "lucide-react";
import { useState } from "react";

import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
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
}

const BOUTON = "flex w-full cursor-pointer items-center rounded-lg text-left text-sm hover:font-medium";

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
            <button
                type="button"
                className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground hover:border-foreground/30 hover:font-medium hover:text-foreground"
                onClick={p.onNouvelleFamille}
            >
                <Plus className="size-3.5" /> {t({ en: "New family", fr: "Nouvelle famille" })}
            </button>
            {groupes.map((g) => (
                <div key={g} className="space-y-0.5">
                    <p className="px-3 pb-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">{GROUPES[g] ? t(GROUPES[g]) : g}</p>
                    {p.familles
                        .filter((f) => f.groupe === g)
                        .map((f) => (
                            <div key={f.slug}>
                                <button
                                    type="button"
                                    className={`${BOUTON} gap-2 px-3 py-1.5 ${p.famille === f.slug ? "bg-accent font-medium text-accent-foreground" : ""}`}
                                    aria-current={p.famille === f.slug}
                                    data-testid={`famille-${f.slug}`}
                                    onClick={() => p.onFamille(f.slug)}
                                >
                                    <BookOpen className="size-3.5 shrink-0" />
                                    <span className="truncate">{f.libelle}</span>
                                </button>
                                {p.famille === f.slug && (
                                    <div className="space-y-0.5" data-testid="sous-dossiers">
                                        {p.dossiers.map((d) => (
                                            <div key={d} className="group flex items-center" style={{ paddingLeft: `${(d.split("/").length - 1) * 0.75}rem` }}>
                                                <button
                                                    type="button"
                                                    className={`${BOUTON} gap-2 py-1 pr-3 pl-8 ${p.dossier === d ? "font-medium text-foreground" : "text-muted-foreground"}`}
                                                    onClick={() => p.onDossier(p.dossier === d ? null : d)}
                                                >
                                                    <Folder className="size-3.5" /> {d.split("/").pop()}
                                                </button>
                                                <button
                                                    type="button"
                                                    className="shrink-0 cursor-pointer px-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100"
                                                    aria-label={t({ en: `Remove the folder ${d}`, fr: `Supprimer le sous-dossier ${d}` })}
                                                    onClick={() => p.onSupprimerDossier(d)}
                                                >
                                                    <X className="size-3" />
                                                </button>
                                            </div>
                                        ))}
                                        {nouveau === null ? (
                                            <button type="button" className={`${BOUTON} gap-2 py-1 pr-3 pl-8 text-xs text-muted-foreground`} onClick={() => setNouveau("")}>
                                                <FolderPlus className="size-3.5" /> {t({ en: "Sub-folder", fr: "Sous-dossier" })}
                                            </button>
                                        ) : (
                                            <div className="py-1 pr-1 pl-8">
                                                <Input
                                                    autoFocus
                                                    value={nouveau}
                                                    placeholder={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                                                    aria-label={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                                                    className="h-7 text-xs"
                                                    onChange={(e) => setNouveau(e.target.value)}
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Enter") creer();
                                                        if (e.key === "Escape") setNouveau(null);
                                                    }}
                                                    onBlur={creer}
                                                />
                                            </div>
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
