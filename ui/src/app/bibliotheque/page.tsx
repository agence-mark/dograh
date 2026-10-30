"use client";

/**
 * [.mark] The « Library » page of the menu (builder-agent-vocal, lot 2): the recipes the builder draws from, with
 * their versions, status and proof. Everyone reads, the .mark team writes.
 */
import { PageBibliotheque } from "@/components/builder/PageBibliotheque";
import { useLangue } from "@/components/mark/langue/langue";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function PageBibliothequeDuMenu() {
    const { t } = useLangue();
    const { user, loading } = useAuth();

    if (loading || !user) {
        return (
            <div className="container mx-auto px-4 py-8">
                <Skeleton className="h-64 w-full max-w-4xl" />
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8" data-testid="page-bibliotheque-menu">
            <div className="mx-auto max-w-4xl space-y-6">
                <div>
                    <h1 className="mb-2 text-3xl font-bold">{t({ en: "Library", fr: "Bibliothèque" })}</h1>
                    <p className="text-muted-foreground">
                        {t({
                            en: "What the builder draws from to build an agent: structures, prompts, sentences, templates, tests. A Candidate is not proven; a Recipe is proven on a bench and accepted by a person.",
                            fr: "Ce que le builder utilise pour construire un agent : structures, prompts, phrases, modèles, tests. Un Candidat n'est pas prouvé ; une Recette est prouvée au banc et acceptée par une personne.",
                        })}
                    </p>
                </div>
                <PageBibliotheque />
            </div>
        </div>
    );
}
