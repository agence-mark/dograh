"use client";

import Link from "next/link";

import { useLangue } from "@/components/mark/langue/langue";

/**
 * Page introuvable (N4) : celle de Next écrit son texte en noir en dur, illisible en mode nuit.
 * Mêmes jetons que le reste de l'écran, deux langues, un lien de retour sans rechargement complet.
 */
export default function NotFound() {
    const { t } = useLangue();
    return (
        <main className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4 text-center">
            <p className="text-5xl font-semibold tracking-tight text-foreground">404</p>
            <p className="text-base font-semibold text-foreground">{t({ en: "Page not found", fr: "Page introuvable" })}</p>
            <Link href="/" className="text-sm text-(--acc-text) hover:font-medium">
                {t({ en: "Back to the home page", fr: "Revenir à l'accueil" })}
            </Link>
        </main>
    );
}
