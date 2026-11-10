"use client";

/**
 * [.mark] Clôture SA-5 (É8, É35) : la barre des listes d'appels de la maquette (`appels-plus.tsx`) : « Chercher un mot », « Tous les motifs »
 * et « Effacer les filtres ». La recherche et le motif sont envoyés au serveur (dans la requête, jamais filtrés ici) ; la saisie part
 * après une courte pause pour ne pas lancer une requête par lettre.
 */
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { ListeDeroulante } from "./liste-deroulante";

export const PAUSE_DE_SAISIE_MS = 350;

/** « 3m 12s » (jamais « 192.0 s »), comme la page Conversations. */
export function dureeLisible(secondes: number) {
    const total = Math.round(secondes);
    const minutes = Math.floor(total / 60);
    const reste = total % 60;
    if (minutes === 0) return `${reste}s`;
    return reste === 0 ? `${minutes}m` : `${minutes}m ${reste}s`;
}

export function RechercheAppels({
    recherche,
    onRecherche,
    motif,
    onMotif,
    motifs,
}: {
    recherche: string;
    onRecherche: (valeur: string) => void;
    motif: string;
    onMotif: (valeur: string) => void;
    motifs: string[];
}) {
    const { t } = useLangue();
    const [saisie, setSaisie] = useState(recherche);
    const derniere = useRef(recherche);
    useEffect(() => {
        // Un effacement venu d'ailleurs (« Effacer les filtres ») vide aussi la saisie.
        if (recherche !== derniere.current) {
            derniere.current = recherche;
            setSaisie(recherche);
        }
    }, [recherche]);
    useEffect(() => {
        if (saisie === derniere.current) return;
        const minuteur = setTimeout(() => {
            derniere.current = saisie;
            onRecherche(saisie);
        }, PAUSE_DE_SAISIE_MS);
        return () => clearTimeout(minuteur);
    }, [saisie, onRecherche]);
    const libelleRecherche = t({ en: "Search a word", fr: "Chercher un mot" });
    const actifs = saisie !== "" || motif !== "";
    return (
        <div className="flex flex-wrap items-center gap-2" data-barre="recherche-appels">
            <div className="relative w-full max-w-72">
                <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input
                    value={saisie}
                    onChange={(e) => setSaisie(e.target.value)}
                    maxLength={80}
                    aria-label={libelleRecherche}
                    placeholder={libelleRecherche}
                    className="h-9 border-transparent bg-muted/50 pl-9 shadow-none"
                />
            </div>
            <ListeDeroulante
                value={motif}
                onChange={(e) => onMotif(e.target.value)}
                aria-label={t({ en: "Reason", fr: "Motif" })}
                className="w-48"
            >
                <option value="">{t({ en: "All reasons", fr: "Tous les motifs" })}</option>
                {motifs.map((m) => (
                    <option key={m} value={m}>
                        {m}
                    </option>
                ))}
            </ListeDeroulante>
            {actifs && (
                <Button
                    variant="ghost"
                    size="sm"
                    className="hover:font-semibold"
                    onClick={() => {
                        derniere.current = "";
                        setSaisie("");
                        onRecherche("");
                        onMotif("");
                    }}
                >
                    {t({ en: "Clear filters", fr: "Effacer les filtres" })}
                </Button>
            )}
        </div>
    );
}
