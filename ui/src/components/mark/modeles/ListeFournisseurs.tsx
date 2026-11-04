"use client";

/**
 * [.mark] V2b (E51) : la colonne des fournisseurs de la fenêtre d'un service, comme la maquette : un champ de
 * recherche (« 16 fournisseurs »), la liste, une coche sur celui qui est choisi. Les fournisseurs viennent du schéma
 * du serveur : un fournisseur ajouté au serveur apparaît ici sans toucher à cet écran.
 */
import { Check } from "lucide-react";
import { useState } from "react";

import { Input } from "@/components/ui/input";

import { useLangue } from "../langue/langue";

export function ListeFournisseurs({
    fournisseurs,
    choisi,
    choisir,
    libelle,
}: {
    fournisseurs: { id: string; nom: string }[];
    choisi: string;
    choisir: (id: string) => void;
    /** Pour les lecteurs d'écran : à quoi sert la liste. */
    libelle: string;
}) {
    const { t } = useLangue();
    const [cherche, setCherche] = useState("");
    const visibles = fournisseurs.filter((f) => f.nom.toLowerCase().includes(cherche.trim().toLowerCase()));
    const n = fournisseurs.length;
    return (
        <div className="flex max-h-[55vh] flex-col border-r pr-2">
            <Input
                value={cherche}
                onChange={(e) => setCherche(e.target.value)}
                placeholder={t({ en: `${n} providers`, fr: `${n} fournisseurs` })}
                aria-label={t({ en: "Search a provider", fr: "Chercher un fournisseur" })}
                className="mb-2 h-8"
            />
            <div role="listbox" aria-label={libelle} className="overflow-auto">
                {visibles.map((f) => (
                    <button
                        key={f.id}
                        type="button"
                        role="option"
                        aria-selected={choisi === f.id}
                        onClick={() => choisir(f.id)}
                        className={`flex w-full cursor-pointer items-center rounded-md px-3 py-1.5 text-left text-sm ${
                            choisi === f.id ? "bg-muted font-medium" : "hover:bg-muted/50 hover:font-medium"
                        }`}
                    >
                        <span className="flex-1">{f.nom}</span>
                        {choisi === f.id && <Check className="size-3.5" aria-hidden />}
                    </button>
                ))}
            </div>
        </div>
    );
}
