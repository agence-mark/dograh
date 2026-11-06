"use client";

/**
 * [.mark] Partie 3, sous-lot 11 (SE-17, F-5) : une date relative partout (« aujourd'hui 17:22 », « hier 09:05 », puis « 04/11 00:32 »),
 * la date complète au survol. Un seul composant pour tous les tableaux (À améliorer, Alertes, Conversations, Campagnes, Agents,
 * Versions) : le jour se compte dans le fuseau de l'organisation quand il est connu.
 */
import { useLangue } from "@/components/mark/langue/langue";
import { formatDateRelative, formatDateTime } from "@/lib/dateTime";

export function DateRelative({ valeur, fuseau, vide = "" }: { valeur: string | number | Date | null | undefined; fuseau?: string | null; vide?: string }) {
    const { langue } = useLangue();
    if (valeur === null || valeur === undefined || valeur === "") return <>{vide}</>;
    const date = new Date(valeur);
    if (Number.isNaN(date.getTime())) return <>{vide}</>;
    const l = langue === "fr" ? "fr" : "en";
    return (
        <time dateTime={date.toISOString()} title={formatDateTime(date, fuseau, l)}>
            {formatDateRelative(date, l, fuseau)}
        </time>
    );
}
