"use client";

/**
 * [.mark] The « Library » page of the menu (builder-agent-vocal, lot 2): the recipes the builder draws from, with
 * their versions, status and proof. Everyone reads, the .mark team writes. K5: the title and the frame come from
 * the page itself (`PageStudio`), as in the maquette.
 */
import { PageBibliotheque } from "@/components/builder/PageBibliotheque";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function PageBibliothequeDuMenu() {
    const { user, loading } = useAuth();

    if (loading || !user) {
        return (
            <PageStudio>
                <Skeleton className="h-64 w-full" />
            </PageStudio>
        );
    }

    return (
        <PageStudio>
            <div data-testid="page-bibliotheque-menu">
                <PageBibliotheque />
            </div>
        </PageStudio>
    );
}
