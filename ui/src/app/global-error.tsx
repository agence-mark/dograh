"use client";

import "./globals.css";
import "./mark-theme.css";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

import { FournisseurLangue, useLangue } from "@/components/mark/langue/langue";

/**
 * [.mark] Erreur qui remonte jusqu'à la racine (V2) : la page d'erreur par défaut de Next est en anglais et sans les
 * jetons de l'écran (blanche en mode nuit). Mêmes jetons, deux langues, une seule action : réessayer. Jamais le texte
 * de l'erreur à l'écran (il part à Sentry).
 */
function Contenu({ reessayer }: { reessayer?: () => void }) {
    const { t } = useLangue();
    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-4 text-center text-foreground">
            <p className="text-base font-semibold">{t({ en: "This page ran into a problem", fr: "Quelque chose s'est mal passé" })}</p>
            <p className="max-w-sm text-sm text-muted-foreground">
                {t({ en: "The page could not be displayed. Try again, or come back in a moment.", fr: "La page n'a pas pu s'afficher. Réessayez, ou revenez dans un instant." })}
            </p>
            <button
                type="button"
                onClick={() => (reessayer ? reessayer() : window.location.reload())}
                className="mt-1 cursor-pointer text-sm text-(--acc-text) hover:font-medium"
            >
                {t({ en: "Try again", fr: "Réessayer" })}
            </button>
        </main>
    );
}

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset?: () => void }) {
    useEffect(() => {
        Sentry.captureException(error);
    }, [error]);

    return (
        <html lang="fr" suppressHydrationWarning>
            <head>
                <script
                    dangerouslySetInnerHTML={{
                        __html: `try{if(localStorage.getItem('theme')==='dark')document.documentElement.classList.add('dark')}catch(e){}`,
                    }}
                />
            </head>
            <body>
                <FournisseurLangue>
                    <Contenu reessayer={reset} />
                </FournisseurLangue>
            </body>
        </html>
    );
}
