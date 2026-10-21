"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 : ce que la voix dit sans passer par une règle du thème, montré EN LECTURE
 * sous la liste (F24, repris de l'ancienne carte) : les phrases écrites dans le graphe (accueil, portes, fins
 * figées) et celles que dit une action quand elle s'exécute. Elles se règlent ailleurs, avec un lien.
 */
import Link from "next/link";

import { Intertitre } from "../../ecran/Intertitre";
import { type Texte, useLangue } from "../../langue/langue";
import type { AgentDeLaCarte, Carte } from "./donnees";

const NATURES: Record<string, Texte> = {
    accueil: { en: "Greeting", fr: "Accueil" },
    porte: { en: "Step change", fr: "Porte" },
    fin_figee: { en: "Fixed ending", fr: "Fin figée" },
};

const TEXTES = {
    titre: { en: "Said elsewhere (read only)", fr: "Dites ailleurs (en lecture)" },
    description: {
        en: "Sentences written in the graph and on actions: they are set where they are written.",
        fr: "Les phrases écrites dans le graphe et sur les actions : elles se règlent là où elles sont écrites.",
    },
    graphe: { en: "Written in the graph (read only)", fr: "Écrites dans le graphe (en lecture)" },
    ouvrirGraphe: { en: "Open the graph", fr: "Ouvrir le graphe" },
    actions: { en: "Said by an action when it runs (read only, set on the action)", fr: "Dites par une action quand elle s'exécute (en lecture, réglées sur l'action)" },
    erreur: { en: "The map could not be read.", fr: "La carte n'a pas pu être lue." },
    chargement: { en: "Loading…", fr: "Chargement…" },
} satisfies Record<string, Texte>;

export const PhrasesEnLecture = ({ carte, erreur, workflowId }: { carte: Carte | null; erreur: boolean; workflowId: number }) => {
    const { t } = useLangue();
    const agents: AgentDeLaCarte[] = (carte?.agents ?? []).filter((a) => a.lecture.length > 0);
    return (
        <Intertitre id="phrases-lecture" titre={TEXTES.titre} description={TEXTES.description}>
            {!carte && !erreur && <p className="text-xs text-muted-foreground">{t(TEXTES.chargement)}</p>}
            {erreur && (
                <p className="text-xs text-destructive" data-note="carte-illisible">
                    {t(TEXTES.erreur)}
                </p>
            )}
            {agents.map((agent) => (
                <div key={agent.id} className="space-y-1" data-carte-lecture={agent.id}>
                    <p className="text-xs font-medium text-muted-foreground">
                        {carte && carte.agents.length > 1 && (
                            <>
                                <Link href={`/workflow/${agent.id}/settings`} className="underline">
                                    {agent.nom}
                                </Link>{" "}
                                ·{" "}
                            </>
                        )}
                        {t(TEXTES.graphe)} ·{" "}
                        <Link href={`/workflow/${agent.id}`} className="underline">
                            {t(TEXTES.ouvrirGraphe)}
                        </Link>
                    </p>
                    <ul className="space-y-0.5 text-xs">
                        {agent.lecture.map((ligne, i) => (
                            <li key={i}>
                                {t(NATURES[ligne.nature] ?? { en: ligne.nature, fr: ligne.nature })} · {ligne.endroit} : « {ligne.texte} »
                            </li>
                        ))}
                    </ul>
                </div>
            ))}
            {carte && carte.actions.length > 0 && workflowId >= 0 && (
                <div className="space-y-1" data-carte-actions>
                    <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.actions)}</p>
                    <ul className="list-disc space-y-0.5 pl-5 text-xs">
                        {carte.actions.map((a, i) => (
                            <li key={i}>{a.description}</li>
                        ))}
                    </ul>
                </div>
            )}
        </Intertitre>
    );
};
