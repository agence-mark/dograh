"use client";

/**
 * [.mark] U12 (E104, point 5) : la mise à jour en direct. L'écran ouvert sur un élément écoute `GET /builder/live?objet=...` (SSE) ;
 * chaque écriture (MCP, builder de l'écran, collègue) arrive ici. `LigneLive` dit « Modifié par Claude Code (Evan) · à l'instant »
 * pendant quelques secondes, et appelle `quand` pour que l'écran se relise seul.
 * Le flux se ferme côté serveur au bout de dix minutes : il se rouvre à partir du dernier identifiant reçu.
 */
import { Terminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { suivreLesModificationsApiV1BuilderLiveGet } from "@/client";
import { lireLesBlocs } from "@/components/builder/chat/evenements";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { useAuth } from "@/lib/auth";

export type Modification = { objet: string; action: string; source: "claude_code" | "ecran" | "collegue"; auteur: string | null; le: string | null };

const REPRISE_MS = 2000;
const VISIBLE_MS = 6000;

const T = {
    claudeCode: { en: "Modified by Claude Code", fr: "Modifié par Claude Code" },
    parAutre: { en: "Modified by", fr: "Modifié par" },
    instant: { en: "just now", fr: "à l'instant" },
} satisfies Record<string, Texte>;

/** Écoute les modifications d'un objet (ex. `agent:12`) ; `quand` est appelée à chacune. */
export function useModifications(objet: string | null, quand: (m: Modification) => void) {
    const { user, loading: authLoading } = useAuth();
    const rappel = useRef(quand);
    rappel.current = quand;

    useEffect(() => {
        if (authLoading || !user || !objet) return;
        const arret = new AbortController();
        let vivant = true;
        let dernier: number | undefined;
        (async () => {
            while (vivant) {
                try {
                    const r = await suivreLesModificationsApiV1BuilderLiveGet({
                        query: { objet, ...(dernier !== undefined ? { depuis: dernier } : {}) },
                        parseAs: "stream",
                        signal: arret.signal,
                    });
                    if (!r.error && r.data) {
                        for await (const { id, evenement } of lireLesBlocs(r.data as ReadableStream<Uint8Array>)) {
                            dernier = id;
                            rappel.current(evenement as unknown as Modification);
                        }
                    }
                } catch (e) {
                    if ((e as { name?: string })?.name === "AbortError") return;
                }
                await new Promise((ok) => setTimeout(ok, REPRISE_MS));
            }
        })();
        return () => {
            vivant = false;
            arret.abort();
        };
    }, [authLoading, user, objet]);
}

/** « Modifié par Claude Code (Evan) · à l'instant » : visible quelques secondes après une écriture de Claude Code. */
export function LigneLive({ objet, quand }: { objet: string; quand?: (m: Modification) => void }) {
    const { t } = useLangue();
    const [vue, setVue] = useState<Modification | null>(null);
    const minuteur = useRef<ReturnType<typeof setTimeout>>(undefined);

    useModifications(objet, (m) => {
        quand?.(m);
        if (m.source !== "claude_code") return;
        setVue(m);
        clearTimeout(minuteur.current);
        minuteur.current = setTimeout(() => setVue(null), VISIBLE_MS);
    });
    useEffect(() => () => clearTimeout(minuteur.current), []);

    if (!vue) return null;
    return (
        <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
            <Terminal className="size-3.5 text-(--acc)" aria-hidden />
            {t(T.claudeCode)}
            {vue.auteur ? ` (${vue.auteur})` : ""} · {t(T.instant)}
        </p>
    );
}
