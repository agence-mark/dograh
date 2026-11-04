"use client";

/**
 * [.mark] U8 (lots C, D, E) : les indicateurs de « Qualité » (reprise de `app/labo/qualite/page.tsx` de la maquette).
 * Une bande de cinq chiffres, les motifs d'appel et leur taux de résolution, la comparaison des versions en ligne (l'effet
 * d'une publication), puis le tableau par agent. Tout est calculé par `GET /qualite` depuis le journal des appels : aucune donnée
 * écrite ici. 7 ou 30 jours.
 */
import { ArrowRightLeft, BarChart3, Clock, PhoneOff, Star, Target } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { lireLaQualiteApiV1QualiteGet } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info, NoteJuge } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

import { BandeChiffres } from "./BandeChiffres";

type Resume = {
    appels: number;
    appels_mesures: number;
    juges: number;
    note: number | null;
    issues: number;
    part_issue: number | null;
    transferts: number;
    part_transferts: number | null;
    raccroches: number;
    part_raccroches: number | null;
    part_impasse: number | null;
    reponse_mediane: number | null;
    cout: number | null;
};
type Agent = Resume & { workflow_id: number; workflow_nom: string; version: number | null };
type Version = Resume & { workflow_id: number; workflow_nom: string; version: number };
type Qualite = {
    jours: number;
    global: Resume;
    motifs: { motif: string; appels: number; part_resolu: number | null }[];
    agents: Agent[];
    versions: Version[];
};

const T = {
    info: {
        en: "Computed from each call's event journal: no new data is stored. A publication leaves a line: the effect of a correction shows.",
        fr: "Tout est calculé depuis le journal d'événements de chaque appel, aucune donnée nouvelle n'est stockée. Une publication trace une ligne : on voit l'effet d'une correction.",
    },
    sept: { en: "7 days", fr: "7 jours" },
    trente: { en: "30 days", fr: "30 jours" },
    note: { en: "Judge's score", fr: "Note du juge" },
    notePhrase: { en: "out of 5", fr: "sur 5" },
    jugesCalls: { en: "calls judged", fr: "appels jugés" },
    issue: { en: "Outcome obtained by a tool", fr: "Issue obtenue par un outil" },
    issuePhrase: { en: "appointment, request, transfer", fr: "rendez-vous, demande, transfert" },
    transferts: { en: "Transfers", fr: "Transferts" },
    raccroches: { en: "Hung up before the end", fr: "Raccrochés avant la fin" },
    appels: { en: "calls", fr: "appels" },
    reponse: { en: "Median response", fr: "Réponse médiane" },
    reponsePhrase: { en: "per turn, tools included", fr: "par tour, outils compris" },
    motifs: { en: "Call reasons and resolution rate", fr: "Motifs d'appel et taux de résolution" },
    motifsInfo: {
        en: "The reason is read in the agent's sheet (a closed list per agent); the rate is the share of its calls that obtained an outcome.",
        fr: "Le motif est lu dans la fiche de l'agent (une liste fermée par agent) ; le taux est la part de ses appels qui ont obtenu une issue.",
    },
    versions: { en: "Before and after a publication", fr: "Avant et après une publication" },
    versionsInfo: {
        en: "Each call carries the version that led it. The versions seen in the period are compared, the newest first.",
        fr: "Chaque appel porte la version qui l'a mené. On compare les versions vues dans la période, la plus récente d'abord.",
    },
    parAgent: { en: "By agent", fr: "Par agent" },
    agent: { en: "Agent", fr: "Agent" },
    version: { en: "Version", fr: "Version" },
    appelsCol: { en: "Calls", fr: "Appels" },
    noteCol: { en: "Score", fr: "Note" },
    issueCol: { en: "Outcome", fr: "Issue" },
    impasseCol: { en: "Dead ends", fr: "Impasses" },
    reponseCol: { en: "Response", fr: "Réponse" },
    coutCol: { en: "Cost", fr: "Coût" },
    aucun: { en: "No call yet", fr: "Aucun appel encore" },
};

const pct = (x: number | null) => (x == null ? "–" : `${Math.round(x * 100)} %`);
const virgule = (x: number | null, d = 1) => (x == null ? "–" : x.toFixed(d).replace(".", ","));

export function OngletIndicateurs() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [jours, setJours] = useState<7 | 30>(7);
    const [etat, setEtat] = useState<"chargement" | "erreur" | Qualite>("chargement");

    const charger = useCallback(async () => {
        setEtat("chargement");
        const r = await lireLaQualiteApiV1QualiteGet({ query: { jours } });
        setEtat(r.error || !r.data ? "erreur" : (r.data as unknown as Qualite));
    }, [jours]);

    useEffect(() => {
        if (loading || !user) return;
        void charger();
    }, [loading, user, charger]);

    if (etat === "chargement") return <EtatVide cas="chargement" />;
    if (etat === "erreur") return <EtatVide cas="erreur" reessayer={() => void charger()} />;
    const g = etat.global;
    const periode = (
        <div className="flex items-center gap-1">
            {([7, 30] as const).map((j) => (
                <Button key={j} size="sm" variant={jours === j ? "secondary" : "ghost"} onClick={() => setJours(j)}>
                    {t(j === 7 ? T.sept : T.trente)}
                </Button>
            ))}
        </div>
    );
    if (g.appels === 0) {
        return (
            <div className="space-y-4">
                <div className="flex justify-end">{periode}</div>
                <EtatVide cas="premier" icone={BarChart3} titre={t(T.aucun)} info={t(T.info)} />
            </div>
        );
    }

    return (
        <div className="space-y-12">
            <div className="flex items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    {t(jours === 7 ? T.sept : T.trente)}
                    <Info>{t(T.info)}</Info>
                </p>
                {periode}
            </div>
            <BandeChiffres
                colonnes={5}
                chiffres={[
                    { icone: Star, libelle: t(T.note), valeur: virgule(g.note), phrase: `${t(T.notePhrase)}, ${g.juges} ${t(T.jugesCalls)}` },
                    { icone: Target, libelle: t(T.issue), valeur: pct(g.part_issue), phrase: t(T.issuePhrase) },
                    { icone: ArrowRightLeft, libelle: t(T.transferts), valeur: pct(g.part_transferts), phrase: `${g.transferts} ${t(T.appels)}` },
                    { icone: PhoneOff, libelle: t(T.raccroches), valeur: pct(g.part_raccroches), phrase: `${g.raccroches} ${t(T.appels)}` },
                    { icone: Clock, libelle: t(T.reponse), valeur: g.reponse_mediane == null ? "–" : `${virgule(g.reponse_mediane)} s`, phrase: t(T.reponsePhrase) },
                ]}
            />
            {etat.motifs.length > 0 && (
                <div>
                    <TitreTableau titre={t(T.motifs)} info={<Info>{t(T.motifsInfo)}</Info>} />
                    <ul className="divide-y">
                        {etat.motifs.map((m) => (
                            <li key={m.motif} className="flex items-center gap-4 py-3 text-sm">
                                <span className="flex-1">{m.motif}</span>
                                <span className="w-24 text-right text-muted-foreground">
                                    {m.appels} {t(T.appels)}
                                </span>
                                <div className="h-2 w-28 overflow-hidden rounded-full bg-muted">
                                    <div
                                        className={`h-full ${(m.part_resolu ?? 0) < 0.7 ? "bg-(--pastille-urgente)" : "bg-foreground"}`}
                                        style={{ width: `${Math.round((m.part_resolu ?? 0) * 100)}%` }}
                                    />
                                </div>
                                <span className="w-12 text-right tabular-nums">{pct(m.part_resolu)}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {etat.versions.length > 0 && (
                <div>
                    <TitreTableau titre={t(T.versions)} info={<Info>{t(T.versionsInfo)}</Info>} />
                    <Tableau
                        colonnes={[
                            { titre: t(T.agent) },
                            { titre: t(T.version) },
                            { titre: t(T.appelsCol), droite: true },
                            { titre: t(T.issueCol), droite: true },
                            { titre: t(T.impasseCol), droite: true },
                            { titre: t(T.noteCol), droite: true },
                            { titre: t(T.reponseCol), droite: true },
                            { titre: t(T.coutCol), droite: true },
                        ]}
                    >
                        {etat.versions.map((v) => (
                            <Ligne key={`${v.workflow_id}-${v.version}`}>
                                <Cellule principale>{v.workflow_nom}</Cellule>
                                <Cellule>v{v.version}</Cellule>
                                <Cellule droite>{v.appels}</Cellule>
                                <Cellule droite>{pct(v.part_issue)}</Cellule>
                                <Cellule droite>{pct(v.part_impasse)}</Cellule>
                                <Cellule droite>
                                    <NoteJuge note={v.note} />
                                </Cellule>
                                <Cellule droite>{v.reponse_mediane == null ? "–" : `${virgule(v.reponse_mediane)} s`}</Cellule>
                                <Cellule droite>{v.cout == null ? "–" : `${v.cout.toFixed(2).replace(".", ",")} $`}</Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                </div>
            )}
            <div>
                <TitreTableau titre={t(T.parAgent)} />
                <Tableau
                    colonnes={[
                        { titre: t(T.agent) },
                        { titre: t(T.version) },
                        { titre: `${t(T.appelsCol)} ${jours} ${t({ en: "d", fr: "j" })}`, droite: true },
                        { titre: t(T.noteCol), droite: true },
                    ]}
                >
                    {etat.agents.map((a) => (
                        <Ligne key={a.workflow_id} href={`/agents/${a.workflow_id}`}>
                            <Cellule principale>{a.workflow_nom}</Cellule>
                            <Cellule>{a.version ? `v${a.version}` : "–"}</Cellule>
                            <Cellule droite>{a.appels}</Cellule>
                            <Cellule droite>
                                <NoteJuge note={a.note} />
                            </Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            </div>
        </div>
    );
}
