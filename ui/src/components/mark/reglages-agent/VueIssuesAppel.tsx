"use client";

/**
 * [.mark] Clôture SA-5 (Evan, 09/11) : la vue « Issues de l'appel » de la maquette de la partie 3 (Réglages › Passages, `VueIssuesAppel`).
 *
 * LECTURE SEULE : les issues ENREGISTRÉES de l'agent (`call_dispositions`) : les issues de départ (celles que le serveur propose) et
 * les siennes, dans l'ordre. Rien ne s'y écrit : « Régler » ouvre l'éditeur du thème Données, là où elles se règlent. Un agent sans
 * issue enregistrée le dit (le classement de fin d'appel est alors éteint).
 */
import { Info } from "@/components/mark/studio/marques";

import { useLangue, type Texte } from "../langue/langue";

type Issue = { code: string; description: string };

const T = {
    titre: { en: "Call outcomes", fr: "Issues de l'appel" },
    info: {
        en: "The outcomes saved for this agent: at the end of a call, a model files the call under one of them and its code is kept. Read only: « Adjust » opens the editor in the Call data theme.",
        fr: "Les issues enregistrées pour cet agent : en fin d'appel, un modèle range l'appel dans l'une d'elles et son code est gardé. Lecture seule : « Régler » ouvre l'éditeur dans le thème Données de l'appel.",
    },
    defaut: { en: "Default", fr: "De départ" },
    propre: { en: "Its own", fr: "Propre à l'agent" },
    proposee: { en: "Proposed, not saved", fr: "Proposée, non enregistrée" },
    regler: { en: "Adjust", fr: "Régler" },
    aucune: {
        en: "No outcome saved: calls are not filed. The starting outcomes below are only proposed; save them in the Call data theme.",
        fr: "Aucune issue enregistrée : les appels ne sont pas classés. Les issues de départ ci-dessous ne sont que proposées ; enregistrez-les dans le thème Données de l'appel.",
    },
} satisfies Record<string, Texte>;

export function VueIssuesAppel({
    issues,
    issuesParDefaut,
    regler,
}: {
    issues: Issue[];
    issuesParDefaut: Issue[];
    /** Ouvre l'éditeur du thème Données, posé sur ce réglage. */
    regler: () => void;
}) {
    const { t } = useLangue();
    const deDepart = new Set(issuesParDefaut.map((i) => i.code.toLowerCase()));
    // Rien d'enregistré : les issues de départ que le serveur propose se montrent (grisées), sans rien écrire.
    const enregistrees = issues.length > 0;
    const lignes = enregistrees ? issues : issuesParDefaut;
    return (
        <section className="space-y-2" data-vue="issues-de-l-appel">
            <p className="flex items-center gap-1.5 text-sm font-semibold">
                {t(T.titre)}
                <Info>{t(T.info)}</Info>
            </p>
            {issues.length === 0 && <p className="border-t py-3 text-sm text-muted-foreground">{t(T.aucune)}</p>}
            {lignes.length > 0 && (
                <ul className="divide-y border-y">
                    {lignes.map((issue, i) => (
                        <li key={issue.code} className={`flex items-center gap-3 py-2.5 text-sm ${enregistrees ? "" : "opacity-70"}`}>
                            <span className="w-5 shrink-0 text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                            <div className="min-w-0 flex-1">
                                <p className="font-mono text-xs font-medium">{issue.code}</p>
                                <p className="line-clamp-2 text-xs text-muted-foreground">{issue.description}</p>
                            </div>
                            <span className="shrink-0 text-xs text-muted-foreground">
                                {!enregistrees ? t(T.proposee) : deDepart.has(issue.code.toLowerCase()) ? t(T.defaut) : t(T.propre)}
                            </span>
                            <button
                                type="button"
                                onClick={regler}
                                aria-label={`${t(T.regler)} : ${issue.code}`}
                                className="shrink-0 cursor-pointer rounded px-2 py-1 text-xs hover:bg-muted hover:font-semibold"
                            >
                                {t(T.regler)}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
