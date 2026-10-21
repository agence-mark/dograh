"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.11, maquette section 6) : la VUE DU GROUPE, sur le principal seulement.
 * Un tableau motif × agent : la phrase EN VIGUEUR de chaque case et d'où elle vient (étape, agent, groupe, défaut), lue
 * dans la carte du serveur, qui résout comme l'appel. Une case du principal ouvre sa règle dans la même fenêtre ;
 * une case d'un spécialisé mène à ses réglages (ses règles s'écrivent dans SA configuration) ; « + propre » crée une
 * règle propre à cet agent (ses réglages s'ouvrent sur l'ajout du motif).
 */
import { Plus, Users } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { type Texte, useLangue } from "../../langue/langue";
import type { Carte, MotifDeLaCarte } from "./donnees";
import { MOTIFS_DE_PHRASES } from "./modele";

export type NiveauDeCellule = "etape" | "agent" | "groupe" | "defaut";

/** Le niveau d'une case : la carte dit « principal » pour une règle du groupe. */
export const niveauDeCellule = (m: MotifDeLaCarte): NiveauDeCellule =>
    m.niveau === "principal" ? "groupe" : m.niveau === "agent" ? "agent" : m.niveau === "etape" ? "etape" : m.etapes.length > 0 && m.niveau !== "defaut" ? "etape" : "defaut";

const STYLES: Record<NiveauDeCellule, string> = {
    etape: "border-primary bg-primary/5",
    agent: "border-foreground/40 bg-background",
    groupe: "border-dashed bg-background",
    defaut: "border-dashed bg-muted/40",
};

const LIBELLES: Record<NiveauDeCellule, Texte> = {
    etape: { en: "specific to a step", fr: "propre à une étape" },
    agent: { en: "specific to the agent", fr: "propre à l'agent" },
    groupe: { en: "group rule (set on the main agent)", fr: "règle du groupe (réglée sur le principal)" },
    defaut: { en: "catalogue default", fr: "défaut du catalogue" },
};

export const VueDuGroupe = ({
    carte,
    workflowId,
    onOuvrir,
    onAjouterPropre,
}: {
    carte: Carte | null;
    workflowId: number;
    /** Une case du principal : ouvre la règle (ou l'ajout du motif quand c'est un défaut). */
    onOuvrir: (motif: string) => void;
    onAjouterPropre: (motif: string) => void;
}) => {
    const { t } = useLangue();
    const agents = carte?.agents ?? [];
    return (
        <Card data-vue-du-groupe>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <Users className="h-4 w-4" />
                    {t({ en: "Fixed sentences of the group", fr: "Phrases fixes du groupe" })}
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                    {t({
                        en: "On the main agent only. One row per cause, one column per agent: the sentence in force and where it comes from. A cell of this agent opens the rule; « + own » creates a rule of that agent.",
                        fr: "Sur le principal seulement. Une ligne par motif, une colonne par agent : la phrase en vigueur et d'où elle vient. Une case de cet agent ouvre la règle ; « + propre » crée une règle propre à l'agent.",
                    })}
                </p>
                <div className="flex flex-wrap gap-2 pt-1 text-[11px]">
                    {(Object.keys(STYLES) as NiveauDeCellule[]).map((n) => (
                        <span key={n} className={`rounded border px-2 py-0.5 ${STYLES[n]}`}>
                            {t(LIBELLES[n])}
                        </span>
                    ))}
                </div>
            </CardHeader>
            <CardContent className="overflow-x-auto">
                {!carte && <p className="text-xs text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>}
                {carte && (
                    <table className="w-full border-separate border-spacing-1.5 text-xs">
                        <thead>
                            <tr>
                                <th className="w-44 text-left font-medium text-muted-foreground">{t({ en: "Cause", fr: "Motif" })}</th>
                                {agents.map((a) => (
                                    <th key={a.id} className="text-left font-semibold">
                                        {a.nom}
                                        {a.id === workflowId ? ` (${t({ en: "main", fr: "principal" })})` : ""}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {MOTIFS_DE_PHRASES.map((motif) => (
                                <tr key={motif.id} data-ligne-groupe={motif.id}>
                                    <td className="pt-2 align-top font-medium">{t(motif.libelle)}</td>
                                    {agents.map((agent) => {
                                        const m = agent.motifs.find((x) => x.motif === motif.id);
                                        const niveau = m ? niveauDeCellule(m) : "defaut";
                                        const texte = m && m.active && m.variantes.length > 0 ? `« ${m.variantes[0]} »` : m && !m.active ? t({ en: "off", fr: "éteinte" }) : "—";
                                        const propre = agent.id === workflowId;
                                        const detail =
                                            niveau === "etape" && m && m.etapes.length > 0
                                                ? t({ en: `step: ${m.etapes.map((e) => e.etape).join(", ")}`, fr: `étape : ${m.etapes.map((e) => e.etape).join(", ")}` })
                                                : niveau === "groupe" && !propre
                                                  ? t({ en: "inherited from the main agent", fr: "héritée du principal" })
                                                  : t(LIBELLES[niveau]);
                                        const contenu = (
                                            <>
                                                <span className="block">{texte}</span>
                                                <span className="mt-1 block text-[10px] text-muted-foreground">{detail}</span>
                                            </>
                                        );
                                        const classe = `block w-full rounded-md border p-2 text-left transition hover:shadow-sm ${STYLES[niveau]} ${m && !m.active ? "text-muted-foreground" : ""}`;
                                        return (
                                            <td key={agent.id} className="align-top" data-case-groupe={`${motif.id}-${agent.id}`} data-niveau={niveau}>
                                                {propre ? (
                                                    <button type="button" className={classe} onClick={() => onOuvrir(motif.id)} aria-label={`${t(motif.libelle)} · ${agent.nom}`}>
                                                        {contenu}
                                                    </button>
                                                ) : (
                                                    <Link href={`/workflow/${agent.id}/settings`} className={classe} aria-label={`${t(motif.libelle)} · ${agent.nom}`}>
                                                        {contenu}
                                                    </Link>
                                                )}
                                                {niveau !== "agent" && niveau !== "etape" && (
                                                    propre ? (
                                                        <button type="button" className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] text-muted-foreground underline" onClick={() => onAjouterPropre(motif.id)}>
                                                            <Plus className="h-3 w-3" />
                                                            {t({ en: "own", fr: "propre" })}
                                                        </button>
                                                    ) : (
                                                        <Link href={`/workflow/${agent.id}/settings?phrases_ajout=${motif.id}`} className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] text-muted-foreground underline">
                                                            <Plus className="h-3 w-3" />
                                                            {t({ en: "own", fr: "propre" })}
                                                        </Link>
                                                    )
                                                )}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </CardContent>
        </Card>
    );
};
