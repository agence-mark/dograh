"use client";

import { AlertCircle, Check, Lock, type LucideIcon } from "lucide-react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { Info } from "./marques";

/**
 * États vides (E102) : un seul composant, six cas. Sobre, centré dans la zone de la liste, sans cadre ni carte.
 * Pas de paragraphe explicatif : une explication passe par « Info ». Symbole seul en couleur, jamais de rond ni
 * de fond pastel. Les couleurs viennent des jetons (`--acc`, `--etat-fait`, `--destructive`).
 *  - premier : rien n'existe encore ; le symbole de la page et un titre court, jamais de bouton.
 *  - fait : une file vide est une bonne nouvelle ; coche verte, titre, une donnée réelle en gris.
 *  - filtre : une recherche ou un filtre sans résultat ; une ligne et « Effacer les filtres ».
 *  - chargement / erreur / acces : à montrer à la place de la liste.
 */
export type EtatVideProps =
    | { cas: "premier"; icone: LucideIcon; titre: string; info?: React.ReactNode }
    | { cas: "fait"; titre: string; donnee?: string; info?: React.ReactNode }
    | { cas: "filtre"; recherche: string; effacer: () => void }
    | { cas: "chargement"; lignes?: number }
    | { cas: "erreur"; reessayer?: () => void }
    | { cas: "acces"; role?: string };

const Centre = ({ children }: { children: React.ReactNode }) => (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 py-8 text-center">{children}</div>
);

export function EtatVide(p: EtatVideProps) {
    const { t } = useLangue();
    if (p.cas === "premier") {
        const I = p.icone;
        return (
            <Centre>
                <I className="size-8 text-(--acc)" strokeWidth={1.75} />
                <p className="flex items-center gap-1.5 text-base font-semibold">
                    {p.titre}
                    {p.info && <Info>{p.info}</Info>}
                </p>
            </Centre>
        );
    }
    if (p.cas === "fait") {
        return (
            <Centre>
                <Check className="size-8 text-(--etat-fait)" strokeWidth={2.25} />
                <p className="flex items-center gap-1.5 text-base font-semibold">
                    {p.titre}
                    {p.info && <Info>{p.info}</Info>}
                </p>
                {p.donnee && <p className="text-sm text-muted-foreground">{p.donnee}</p>}
            </Centre>
        );
    }
    if (p.cas === "filtre") {
        return (
            <Centre>
                <p className="text-sm text-muted-foreground">
                    {t({ en: "No result for", fr: "Aucun résultat pour" })} « {p.recherche} »
                </p>
                <Button variant="ghost" onClick={p.effacer}>
                    {t({ en: "Clear filters", fr: "Effacer les filtres" })}
                </Button>
            </Centre>
        );
    }
    if (p.cas === "chargement") {
        // Des gris pâles à la forme d'une liste : jamais une roue au centre.
        return (
            <div className="divide-y border-y" aria-busy="true" aria-label={t({ en: "Loading", fr: "Chargement" })}>
                {Array.from({ length: p.lignes ?? 4 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-4 py-3.5">
                        <Skeleton className="size-9 rounded-full" />
                        <div className="flex-1 space-y-2">
                            <Skeleton className="h-3.5 w-1/3" />
                            <Skeleton className="h-3 w-2/3" />
                        </div>
                        <Skeleton className="h-3 w-16" />
                    </div>
                ))}
            </div>
        );
    }
    if (p.cas === "erreur") {
        return (
            <Centre>
                <AlertCircle className="size-8 text-destructive" strokeWidth={1.75} />
                <p className="text-base font-semibold">{t({ en: "Unable to load", fr: "Impossible de charger" })}</p>
                {p.reessayer && (
                    <Button variant="outline" onClick={p.reessayer}>
                        {t({ en: "Try again", fr: "Réessayer" })}
                    </Button>
                )}
            </Centre>
        );
    }
    return (
        <Centre>
            <Lock className="size-8 text-muted-foreground" strokeWidth={1.75} />
            <p className="text-base font-semibold">{p.role ?? t({ en: "Reserved for administrators", fr: "Réservé aux administrateurs" })}</p>
        </Centre>
    );
}
