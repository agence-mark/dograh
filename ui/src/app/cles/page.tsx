"use client";

/**
 * [.mark] The « Keys » page of the menu (chantier direct-et-passe-muette, lot 0 bis, P18): the key
 * library of the whole organization, every provider. The same library opens from any setting that
 * takes a key (« Models », an agent's model settings, the simulated caller).
 */
import { BibliothequeCles, DESCRIPTION_BIBLIOTHEQUE } from "@/components/mark/cles/FenetreCles";
import { useLangue } from "@/components/mark/langue/langue";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function PageCles() {
    const { t } = useLangue();
    const { user, loading } = useAuth();

    if (loading || !user) {
        return (
            <div className="container mx-auto px-4 py-8">
                <Skeleton className="h-64 w-full max-w-3xl" />
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8" data-testid="page-cles">
            <div className="mx-auto max-w-3xl space-y-6">
                <div>
                    <h1 className="mb-2 text-3xl font-bold">{t({ en: "Keys", fr: "Clés" })}</h1>
                    <p className="text-muted-foreground">{t(DESCRIPTION_BIBLIOTHEQUE)}</p>
                </div>
                <BibliothequeCles />
            </div>
        </div>
    );
}
