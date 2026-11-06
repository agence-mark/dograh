"use client";

/**
 * [.mark] Partie 3, sous-lot 5 (SE-11, C-3): the « Environment » part of a test window. What the test fixes around the conversation,
 * nothing being really called: the date and time the agent believes it is, the caller's number (or « withheld »), the variables the
 * call starts with, and the answers of the tools in series (« down at the first call, then the answer »). Same shape as the mockup
 * (`tests-plus.tsx`, `EnvironnementTest`). The tools come from the agent; « All other tools » is the server's `*`.
 */
import { Plus, Trash2 } from "lucide-react";

import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import type { EnvironnementServeur, SorteDeReponse } from "./types";

export const TOUT_OUTIL = "*";

export interface AppelSimule {
    sorte: SorteDeReponse;
    corps: string;
}
export interface SimulationEditee {
    outil: string;
    appels: AppelSimule[];
}
export interface EnvironnementEdite {
    date: string;
    heure: string;
    numero: string;
    masque: boolean;
    variables: Array<[string, string]>;
    simulations: SimulationEditee[];
}

export const environnementVide = (): EnvironnementEdite => ({ date: "", heure: "", numero: "", masque: false, variables: [], simulations: [] });

/** The environment of the server as the form edits it. */
export function environnementEdite(s?: EnvironnementServeur | null): EnvironnementEdite {
    if (!s) return environnementVide();
    return {
        date: s.date ?? "",
        heure: s.heure ?? "",
        numero: s.numero ?? "",
        masque: Boolean(s.masque),
        variables: Object.entries(s.variables ?? {}),
        simulations: (s.simulations ?? []).map((m) => ({
            outil: m.outil,
            appels: m.appels.map((a) => ({
                sorte: a.sorte,
                corps: a.sorte === "reponse" && a.corps !== null && a.corps !== undefined ? JSON.stringify(a.corps) : "",
            })),
        })),
    };
}

/** What the server expects. An empty form gives `{}` (on a change, it removes the environment). */
export function environnementPourLeServeur(e: EnvironnementEdite): Record<string, unknown> {
    const variables = Object.fromEntries(e.variables.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), v]));
    const simulations = e.simulations.map((m) => ({
        outil: m.outil,
        appels: m.appels.map((a) => ({ sorte: a.sorte, ...(a.sorte === "reponse" ? { corps: a.corps.trim() } : {}) })),
    }));
    return {
        ...(e.date ? { date: e.date, heure: e.heure } : {}),
        ...(e.masque ? { masque: true } : e.numero.trim() ? { numero: e.numero.trim() } : {}),
        ...(Object.keys(variables).length ? { variables } : {}),
        ...(simulations.length ? { simulations } : {}),
    };
}

const SORTES: Array<{ valeur: SorteDeReponse; fr: string; en: string }> = [
    { valeur: "reponse", fr: "Réponse", en: "Answer" },
    { valeur: "erreur", fr: "Erreur", en: "Error" },
    { valeur: "delai", fr: "Délai dépassé", en: "Timed out" },
    { valeur: "refus", fr: "Refus", en: "Refusal" },
];

const Titre = ({ children, info }: { children: React.ReactNode; info: string }) => (
    <p className="flex items-center gap-1.5 text-sm font-medium">
        {children}
        <Info>{info}</Info>
    </p>
);

export function EnvironnementDuTest({
    valeur,
    changer,
    outils,
}: {
    valeur: EnvironnementEdite;
    changer: (e: EnvironnementEdite) => void;
    /** The tools of the agent (read, never written here). */
    outils: string[];
}) {
    const { t } = useLangue();
    const maj = (suite: Partial<EnvironnementEdite>) => changer({ ...valeur, ...suite });
    const majSimulation = (i: number, s: SimulationEditee) => maj({ simulations: valeur.simulations.map((x, j) => (j === i ? s : x)) });
    const choixDesOutils = [{ valeur: TOUT_OUTIL, libelle: t({ en: "All other tools", fr: "Tous les autres outils" }) }, ...outils.map((o) => ({ valeur: o, libelle: o }))];

    return (
        <div className="space-y-5" data-testid="environnement-du-test">
            <div className="space-y-2">
                <Titre info={t({ en: "The agent believes it is this moment: opening hours, closures, « tomorrow », slots. Empty: the moment the test is played.", fr: "L'agent croit être à ce moment : horaires d'ouverture, fermetures, « demain », créneaux. Vide : le moment où le test est joué." })}>
                    {t({ en: "Date and time of the call", fr: "Date et heure de l'appel" })}
                </Titre>
                <div className="flex gap-2">
                    <Input type="date" value={valeur.date} onChange={(e) => maj({ date: e.target.value, heure: e.target.value ? valeur.heure || "12:00" : "" })} aria-label={t({ en: "Date", fr: "Date" })} className="h-9" />
                    <Input type="time" value={valeur.heure} disabled={!valeur.date} onChange={(e) => maj({ heure: e.target.value })} aria-label={t({ en: "Time", fr: "Heure" })} className="h-9 w-28" />
                </div>
            </div>
            <div className="space-y-2">
                <Titre info={t({ en: "The number shown to the agent: it finds the caller (file, CRM). « Withheld »: the caller does not show a number. A number is replaced by a fictitious one when the test is kept.", fr: "Le numéro présenté à l'agent : il sert à retrouver l'appelant (dossier, CRM). « Masqué » : l'appelant ne présente pas son numéro. Un numéro est remplacé par un numéro fictif quand le test est gardé." })}>
                    {t({ en: "Caller's number", fr: "Numéro de l'appelant" })}
                </Titre>
                <div className="flex items-center gap-3">
                    <Input
                        value={valeur.masque ? "" : valeur.numero}
                        disabled={valeur.masque}
                        onChange={(e) => maj({ numero: e.target.value })}
                        placeholder={valeur.masque ? t({ en: "withheld", fr: "masqué" }) : "06 39 98 00 01"}
                        aria-label={t({ en: "Caller's number", fr: "Numéro de l'appelant" })}
                        className="h-9"
                    />
                    <label className="flex items-center gap-2 whitespace-nowrap text-sm">
                        <Switch checked={valeur.masque} onCheckedChange={(v) => maj({ masque: v })} aria-label={t({ en: "Withheld", fr: "Masqué" })} />
                        {t({ en: "Withheld", fr: "Masqué" })}
                    </label>
                </div>
            </div>
            <div className="space-y-2">
                <Titre info={t({ en: "The variables injected when the call starts (like those the telephony or the widget sets): the test fixes their value.", fr: "Les variables injectées au départ de l'appel (comme celles que pose la téléphonie ou le widget) : le test fixe leur valeur." })}>
                    {t({ en: "Call variables", fr: "Variables de l'appel" })}
                </Titre>
                {valeur.variables.map(([k, v], i) => (
                    <div key={i} className="flex gap-2">
                        <Input value={k} aria-label={t({ en: "Variable name", fr: "Nom de la variable" })} onChange={(e) => maj({ variables: valeur.variables.map((x, j) => (j === i ? [e.target.value, x[1]] : x)) })} className="h-8 font-mono text-xs" />
                        <Input value={v} aria-label={t({ en: "Value", fr: "Valeur" })} onChange={(e) => maj({ variables: valeur.variables.map((x, j) => (j === i ? [x[0], e.target.value] : x)) })} className="h-8 text-xs" />
                        <button type="button" aria-label={t({ en: "Remove the variable", fr: "Retirer la variable" })} onClick={() => maj({ variables: valeur.variables.filter((_, j) => j !== i) })} className="cursor-pointer text-muted-foreground hover:text-foreground">
                            <Trash2 className="size-4" />
                        </button>
                    </div>
                ))}
                <Button variant="outline" size="sm" disabled={valeur.variables.length >= 20} onClick={() => maj({ variables: [...valeur.variables, ["", ""]] })}>
                    <Plus className="size-3.5" /> {t({ en: "Add a variable", fr: "Ajouter une variable" })}
                </Button>
            </div>
            <div className="space-y-2">
                <Titre info={t({ en: "The test touches no real software: each call of the tool receives the answer written here, in order (« down at the first call, then the answer »). Beyond the last, the last repeats. A tool with no simulation answers « done ».", fr: "Le test ne touche aucun vrai logiciel : chaque appel de l'outil reçoit la réponse écrite ici, dans l'ordre (« en panne au premier appel, puis la réponse »). Au-delà de la dernière, la dernière se répète. Un outil sans simulation répond « fait »." })}>
                    {t({ en: "Simulated tool answers", fr: "Réponses d'outils simulées" })}
                </Titre>
                {valeur.simulations.map((s, i) => (
                    <div key={i} className="space-y-2 border-l-2 pl-3">
                        <div className="flex items-center gap-2">
                            <Liste
                                className="flex-1"
                                valeur={s.outil}
                                changer={(v) => majSimulation(i, { ...s, outil: v })}
                                options={s.outil && s.outil !== TOUT_OUTIL && !outils.includes(s.outil) ? [{ valeur: s.outil, libelle: s.outil }, ...choixDesOutils] : choixDesOutils}
                            />
                            <button type="button" aria-label={t({ en: "Remove the simulation", fr: "Retirer la simulation" })} onClick={() => maj({ simulations: valeur.simulations.filter((_, j) => j !== i) })} className="cursor-pointer text-muted-foreground hover:text-foreground">
                                <Trash2 className="size-4" />
                            </button>
                        </div>
                        {s.appels.map((a, k) => (
                            <div key={k} className="space-y-1">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <span className="w-16">
                                        {t({ en: "Call", fr: "Appel" })} {k + 1}
                                    </span>
                                    <Liste
                                        className="w-40"
                                        valeur={a.sorte}
                                        changer={(v) => majSimulation(i, { ...s, appels: s.appels.map((y, m) => (m === k ? { ...y, sorte: v as SorteDeReponse } : y)) })}
                                        options={SORTES.map((x) => ({ valeur: x.valeur, libelle: t(x) }))}
                                    />
                                    {s.appels.length > 1 && (
                                        <button type="button" aria-label={t({ en: "Remove this call", fr: "Retirer cet appel" })} onClick={() => majSimulation(i, { ...s, appels: s.appels.filter((_, m) => m !== k) })} className="cursor-pointer hover:text-foreground">
                                            <Trash2 className="size-3.5" />
                                        </button>
                                    )}
                                </div>
                                {a.sorte === "reponse" && (
                                    <Textarea
                                        rows={2}
                                        value={a.corps}
                                        placeholder="{ }"
                                        aria-label={t({ en: "JSON answer", fr: "Réponse JSON" })}
                                        onChange={(e) => majSimulation(i, { ...s, appels: s.appels.map((y, m) => (m === k ? { ...y, corps: e.target.value } : y)) })}
                                        className="min-h-0 font-mono text-xs"
                                    />
                                )}
                            </div>
                        ))}
                        {s.appels.length < 8 && (
                            <Button variant="ghost" size="sm" className="-ml-2" onClick={() => majSimulation(i, { ...s, appels: [...s.appels, { sorte: "reponse", corps: "{}" }] })}>
                                <Plus className="size-3.5" /> {t({ en: "Next call", fr: "Appel suivant" })}
                            </Button>
                        )}
                    </div>
                ))}
                <Button variant="outline" size="sm" disabled={valeur.simulations.length >= 10} onClick={() => maj({ simulations: [...valeur.simulations, { outil: outils[0] ?? TOUT_OUTIL, appels: [{ sorte: "reponse", corps: "{}" }] }] })}>
                    <Plus className="size-3.5" /> {t({ en: "Simulate a tool", fr: "Simuler un outil" })}
                </Button>
            </div>
        </div>
    );
}
