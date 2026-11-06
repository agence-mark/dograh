"use client";

/**
 * [.mark] U12 (E104, E105) : les marques de ce qui vient de Claude Code. Reprises de la maquette (`components/studio/sources.tsx`) :
 * le petit libellé « Claude Code · Evan », « En direct », la ligne « lecture seule » et la petite carte rouge de l'accueil du builder.
 * La ligne d'avertissement prend les jetons du thème (`--danger-ink`, `bg-destructive`) : aucune couleur écrite à la main.
 */
import { Terminal } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";

const T = {
    claudeCode: { en: "Claude Code", fr: "Claude Code" },
    direct: { en: "Live", fr: "En direct" },
    lecture: { en: "Conversation led in Claude Code: read only", fr: "Conversation menée dans Claude Code : lecture seule" },
    changer: { en: "Change the source", fr: "Changer la source" },
    avertissement: {
        en: "The builder is set to be used in Claude Code through the MCP",
        fr: "Le builder est configuré pour être utilisé sur Claude via le MCP",
    },
} satisfies Record<string, Texte>;

const VERS_SOURCES = "/labo/reglages?onglet=sources";

/** « Claude Code · Evan » : le libellé d'une conversation menée dans Claude Code. */
export function MarqueClaudeCode({ par }: { par?: string | null }) {
    const { t } = useLangue();
    return (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Terminal className="size-3.5 text-(--claude)" aria-hidden />
            {t(T.claudeCode)}
            {par ? ` · ${par}` : ""}
        </span>
    );
}

/** « En direct » : la session tourne, le point pulse. */
export function EnDirect() {
    const { t } = useLangue();
    return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="size-1.5 animate-pulse rounded-full bg-(--signal-ok)" aria-hidden />
            {t(T.direct)}
        </span>
    );
}

/** À la place de la saisie d'une conversation recopiée de Claude Code. */
export function LigneLecture() {
    const { t } = useLangue();
    return (
        <p className="flex items-center gap-2 border-t pt-3 text-sm text-muted-foreground">
            <Terminal className="size-4 text-(--claude)" aria-hidden />
            {t(T.lecture)}
        </p>
    );
}

/** E105, décision 19 : le builder est sur Claude Code, la saisie garde ses informations, l'envoi est fermé ; une ligne douce (point rouge, texte encre) le dit sous la saisie. */
export function AvertissementClaudeCode({ className = "" }: { className?: string }) {
    const { t } = useLangue();
    return (
        <div className={className}>
            <div role="status" className="flex w-fit items-center gap-2 text-sm text-(--danger-ink)">
                <span className="size-1.5 shrink-0 rounded-full bg-destructive" aria-hidden />
                {t(T.avertissement)}
                <Link href={VERS_SOURCES} className="cursor-pointer text-(--link) hover:font-semibold">
                    {t(T.changer)}
                </Link>
            </div>
        </div>
    );
}
