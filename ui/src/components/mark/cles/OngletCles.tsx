"use client";

/**
 * [.mark] K1b : la bibliothèque de clés de l'organisation, onglet de « Modèles et clés » (décision d'Evan, 04/11, comme
 * la maquette : les clés vivent avec les modèles). Même bibliothèque que celle qui s'ouvre depuis chaque réglage qui
 * prend une clé ; l'explication est dans le « ! » du titre, jamais une phrase visible.
 */
import { BibliothequeCles, DESCRIPTION_BIBLIOTHEQUE } from "@/components/mark/cles/FenetreCles";
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { TitreTableau } from "@/components/mark/studio/tableau";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export function OngletCles() {
    const { t } = useLangue();
    const { user, loading } = useAuth();

    if (loading || !user) return <Skeleton className="h-64 w-full max-w-3xl" />;

    return (
        <div data-testid="page-cles" className="space-y-4">
            <TitreTableau titre={t({ en: "Keys", fr: "Clés" })} info={<Info>{t(DESCRIPTION_BIBLIOTHEQUE)}</Info>} />
            <BibliothequeCles />
        </div>
    );
}
