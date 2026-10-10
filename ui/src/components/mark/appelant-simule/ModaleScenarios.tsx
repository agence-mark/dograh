"use client";

/**
 * [.mark] The scenario library of one agent (chantier langwatch-et-fenetre-du-run, lot 3, L10, L18).
 *
 * A scenario is a declaration: who calls and why, extra instructions, behaviours (in a hurry,
 * interrupts, hesitates, goes silent), the judge's criteria, an optional latency threshold, and what
 * a transfer answers. Created, edited, duplicated and removed here; a modal (E4) working on a copy
 * of the agent's list: « Cancel » / « Save ». The words of a trade live in these scenarios, never
 * in the code.
 */
import { Copy, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
    getScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosGet,
    saveScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosPut,
} from "@/client";
import type { Comportements, ScenarioSimule } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

export const COMPORTEMENTS: { champ: keyof Comportements; libelle: Texte }[] = [
    { champ: "presse", libelle: { en: "In a hurry", fr: "Pressé" } },
    { champ: "coupe_la_parole", libelle: { en: "Interrupts", fr: "Coupe la parole" } },
    { champ: "hesite", libelle: { en: "Hesitates", fr: "Hésite" } },
    { champ: "se_tait", libelle: { en: "Goes silent once", fr: "Se tait une fois" } },
];
const RENVOIS: { valeur: ScenarioSimule["renvoi"]; libelle: Texte }[] = [
    { valeur: "refuse", libelle: { en: "Refused", fr: "Refusé" } },
    { valeur: "accepte", libelle: { en: "Accepted", fr: "Accepté" } },
    { valeur: "sans_reponse", libelle: { en: "No answer", fr: "Sans réponse" } },
];

const nouvelId = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export const scenarioVide = (workflowId: number, nom: string): ScenarioSimule => ({
    id: nouvelId(),
    workflow_id: workflowId,
    nom,
    role: "",
    consigne: "",
    comportements: { presse: false, coupe_la_parole: false, hesite: false, se_tait: false },
    criteres: [""],
    tours_max: 12,
    renvoi: "refuse",
    latence_max_s: null,
});

/** The faults of the draft, named (the server checks the same). */
export const fautesDesScenarios = (scenarios: ScenarioSimule[], t: (texte: Texte) => string): string[] => {
    const fautes: string[] = [];
    const noms = new Set<string>();
    scenarios.forEach((s, i) => {
        const n = s.nom.trim() || `#${i + 1}`;
        if (!s.nom.trim()) fautes.push(t({ en: `Scenario ${i + 1}: name missing`, fr: `Scénario ${i + 1} : nom manquant` }));
        if (!s.role.trim()) fautes.push(t({ en: `${n}: caller role missing`, fr: `${n} : rôle de l'appelant manquant` }));
        if (!s.criteres.some((c) => c.trim()))
            fautes.push(t({ en: `${n}: at least one criterion`, fr: `${n} : au moins un critère` }));
        const tours = s.tours_max ?? 12;
        if (tours < 2 || tours > 40) fautes.push(t({ en: `${n}: 2 to 40 turns`, fr: `${n} : 2 à 40 tours` }));
        const latence = s.latence_max_s;
        if (latence !== null && latence !== undefined && (latence < 0.5 || latence > 30))
            fautes.push(t({ en: `${n}: latency threshold 0.5 to 30 s`, fr: `${n} : seuil de latence de 0,5 à 30 s` }));
        const cle = s.nom.trim().toLowerCase();
        if (cle && noms.has(cle)) fautes.push(t({ en: `${n}: name used twice`, fr: `${n} : nom utilisé deux fois` }));
        noms.add(cle);
    });
    return fautes;
};

/** The expected record as text, one « field = value » per line (a value left empty: must stay empty). */
export const ficheAttendueEnTexte = (fiche: ScenarioSimule["fiche_attendue"]): string =>
    Object.entries(fiche ?? {})
        .map(([champ, valeur]) => `${champ} = ${valeur ?? ""}`)
        .join("\n");

/** The text back to the expected record; null when no line names a field. */
export const texteEnFicheAttendue = (texte: string): ScenarioSimule["fiche_attendue"] => {
    const fiche: Record<string, string | null> = {};
    for (const ligne of texte.split("\n")) {
        const coupe = ligne.indexOf("=");
        const champ = (coupe === -1 ? ligne : ligne.slice(0, coupe)).trim();
        if (!champ) continue;
        const valeur = coupe === -1 ? "" : ligne.slice(coupe + 1).trim();
        fiche[champ] = valeur === "" ? null : valeur;
    }
    return Object.keys(fiche).length ? fiche : null;
};

const nettoyer = (s: ScenarioSimule): ScenarioSimule => ({
    ...s,
    nom: s.nom.trim(),
    criteres: s.criteres.map((c) => c.trim()).filter(Boolean),
});

function EditeurScenario({
    scenario,
    onChange,
}: {
    scenario: ScenarioSimule;
    onChange: (morceau: Partial<ScenarioSimule>) => void;
}) {
    const { t } = useLangue();
    // The text being typed is kept apart from the parsed record, or a half-typed line would vanish.
    const [ficheTexte, setFicheTexte] = useState(() => ficheAttendueEnTexte(scenario.fiche_attendue));
    useEffect(() => setFicheTexte(ficheAttendueEnTexte(scenario.fiche_attendue)), [scenario.id]); // eslint-disable-line react-hooks/exhaustive-deps
    return (
        <div className="space-y-3" data-testid="editeur-scenario">
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>{t({ en: "Name", fr: "Nom" })}</span>
                <Input
                    value={scenario.nom}
                    onChange={(e) => onChange({ nom: e.target.value })}
                    aria-label={t({ en: "Scenario name", fr: "Nom du scénario" })}
                />
            </label>
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>
                    {t({
                        en: "Who calls and why (what the simulated caller knows and wants)",
                        fr: "Qui appelle et pourquoi (ce que l'appelant simulé sait et veut)",
                    })}
                </span>
                <Textarea
                    value={scenario.role}
                    onChange={(e) => onChange({ role: e.target.value })}
                    className="min-h-24 text-sm"
                    aria-label={t({ en: "Caller role", fr: "Rôle de l'appelant" })}
                />
            </label>
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>{t({ en: "Extra instructions (optional)", fr: "Consignes en plus (facultatif)" })}</span>
                <Textarea
                    value={scenario.consigne ?? ""}
                    onChange={(e) => onChange({ consigne: e.target.value })}
                    className="min-h-16 text-sm"
                    aria-label={t({ en: "Extra instructions", fr: "Consignes en plus" })}
                />
            </label>
            <fieldset className="flex flex-wrap gap-4 text-sm">
                <legend className="mb-1 text-xs text-muted-foreground">{t({ en: "Behaviours", fr: "Comportements" })}</legend>
                {COMPORTEMENTS.map(({ champ, libelle }) => (
                    <label key={champ} className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            checked={Boolean(scenario.comportements?.[champ])}
                            onChange={(e) =>
                                onChange({
                                    comportements: {
                                        presse: false,
                                        coupe_la_parole: false,
                                        hesite: false,
                                        se_tait: false,
                                        ...scenario.comportements,
                                        [champ]: e.target.checked,
                                    },
                                })
                            }
                        />
                        {t(libelle)}
                    </label>
                ))}
            </fieldset>
            <div className="space-y-1">
                <span className="text-xs text-muted-foreground">
                    {t({ en: "Judge's criteria (one per line, in plain words)", fr: "Critères du juge (un par ligne, en phrases)" })}
                </span>
                {scenario.criteres.map((critere, i) => (
                    <div key={i} className="flex gap-2">
                        <Input
                            value={critere}
                            onChange={(e) =>
                                onChange({ criteres: scenario.criteres.map((c, k) => (k === i ? e.target.value : c)) })
                            }
                            aria-label={t({ en: `Criterion ${i + 1}`, fr: `Critère ${i + 1}` })}
                        />
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => onChange({ criteres: scenario.criteres.filter((_, k) => k !== i) })}
                            aria-label={t({ en: "Remove the criterion", fr: "Retirer le critère" })}
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    </div>
                ))}
                <Button variant="outline" size="sm" onClick={() => onChange({ criteres: [...scenario.criteres, ""] })}>
                    <Plus className="mr-1 h-4 w-4" />
                    {t({ en: "Add a criterion", fr: "Ajouter un critère" })}
                </Button>
            </div>
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>
                    {t({
                        en: "Expected call record (optional, one « field = value » per line; no value: the field must stay empty)",
                        fr: "Fiche attendue (facultatif, un « champ = valeur » par ligne ; sans valeur : le champ doit rester vide)",
                    })}
                </span>
                <Textarea
                    value={ficheTexte}
                    onChange={(e) => {
                        setFicheTexte(e.target.value);
                        onChange({ fiche_attendue: texteEnFicheAttendue(e.target.value) });
                    }}
                    className="min-h-16 font-mono text-sm"
                    aria-label={t({ en: "Expected call record", fr: "Fiche attendue" })}
                />
            </label>
            <div className="grid gap-2 sm:grid-cols-3">
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Turns at most", fr: "Tours au plus" })}</span>
                    <Input
                        type="number"
                        min={2}
                        max={40}
                        value={scenario.tours_max ?? 12}
                        onChange={(e) => onChange({ tours_max: Number(e.target.value) })}
                        aria-label={t({ en: "Turns at most", fr: "Tours au plus" })}
                    />
                </label>
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Fail if a turn is slower than (s, optional)", fr: "Échec si un tour dépasse (s, facultatif)" })}</span>
                    <Input
                        type="number"
                        min={0.5}
                        max={30}
                        step="0.5"
                        value={scenario.latence_max_s ?? ""}
                        onChange={(e) => onChange({ latence_max_s: e.target.value === "" ? null : Number(e.target.value) })}
                        aria-label={t({ en: "Latency threshold", fr: "Seuil de latence" })}
                    />
                </label>
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "If the agent transfers the call", fr: "Si l'agent renvoie l'appel" })}</span>
                    <select
                        className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                        value={scenario.renvoi ?? "refuse"}
                        onChange={(e) => onChange({ renvoi: e.target.value as ScenarioSimule["renvoi"] })}
                        aria-label={t({ en: "Transfer answer", fr: "Réponse au renvoi" })}
                    >
                        {RENVOIS.map((r) => (
                            <option key={r.valeur} value={r.valeur}>
                                {t(r.libelle)}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
        </div>
    );
}

export function ModaleScenarios({
    workflowId,
    ouverte,
    onFermer,
}: {
    workflowId: number;
    ouverte: boolean;
    onFermer: (enregistre: boolean) => void;
}) {
    const { t } = useLangue();
    const [brouillon, setBrouillon] = useState<ScenarioSimule[] | null>(null);
    const [choisi, setChoisi] = useState(0);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        let annule = false;
        setErreur(null);
        setBrouillon(null);
        setChoisi(0);
        (async () => {
            const reponse = await getScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosGet({
                path: { workflow_id: workflowId },
            });
            if (annule) return;
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Scenario library unreadable"));
                return;
            }
            setBrouillon((reponse.data as ScenarioSimule[]) ?? []);
        })();
        return () => {
            annule = true;
        };
    }, [ouverte, workflowId]);

    const fautes = brouillon ? fautesDesScenarios(brouillon, t) : [];
    const courant = brouillon?.[choisi];
    const changer = (morceau: Partial<ScenarioSimule>) =>
        setBrouillon((avant) => (avant ? avant.map((s, k) => (k === choisi ? { ...s, ...morceau } : s)) : avant));
    const ajouter = (scenario: ScenarioSimule) => {
        setBrouillon((avant) => [...(avant ?? []), scenario]);
        setChoisi(brouillon?.length ?? 0);
    };

    const enregistrer = async () => {
        if (!brouillon) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await saveScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosPut({
            path: { workflow_id: workflowId },
            body: brouillon.map(nettoyer),
        });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Scenarios not saved"));
            return;
        }
        onFermer(true);
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(false))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl" data-testid="modale-scenarios">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Scenarios of this agent", fr: "Scénarios de cet agent" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Each scenario says who calls, why, how they behave, and what the judge checks. The simulated caller plays it against the agent; the judge gives the verdict.",
                            fr: "Chaque scénario dit qui appelle, pourquoi, comment il se comporte, et ce que le juge vérifie. L'appelant simulé le joue face à l'agent ; le juge rend le verdict.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert">
                        {erreur}
                    </p>
                )}
                {brouillon === null && !erreur ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : brouillon ? (
                    <div className="grid gap-4 sm:grid-cols-[14rem_1fr]">
                        <div className="space-y-2">
                            <ul className="space-y-1" data-testid="liste-scenarios">
                                {brouillon.map((s, i) => (
                                    <li key={s.id} className="flex items-center gap-1">
                                        <button
                                            type="button"
                                            onClick={() => setChoisi(i)}
                                            className={`flex-1 truncate rounded px-2 py-1 text-left text-sm ${
                                                i === choisi ? "bg-muted font-medium" : "hover:bg-muted/60"
                                            }`}
                                        >
                                            {s.nom.trim() || t({ en: "(no name)", fr: "(sans nom)" })}
                                        </button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() =>
                                                ajouter({
                                                    ...s,
                                                    id: nouvelId(),
                                                    nom: t({ en: `${s.nom} (copy)`, fr: `${s.nom} (copie)` }),
                                                })
                                            }
                                            aria-label={t({ en: `Duplicate ${s.nom}`, fr: `Dupliquer ${s.nom}` })}
                                        >
                                            <Copy className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => {
                                                setBrouillon((avant) => (avant ?? []).filter((_, k) => k !== i));
                                                setChoisi(0);
                                            }}
                                            aria-label={t({ en: `Remove ${s.nom}`, fr: `Retirer ${s.nom}` })}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </li>
                                ))}
                            </ul>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                    ajouter(scenarioVide(workflowId, t({ en: "New scenario", fr: "Nouveau scénario" })))
                                }
                            >
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "New scenario", fr: "Nouveau scénario" })}
                            </Button>
                        </div>
                        {courant ? (
                            <EditeurScenario scenario={courant} onChange={changer} />
                        ) : (
                            <p className="text-sm text-muted-foreground">
                                {t({ en: "No scenario yet for this agent.", fr: "Aucun scénario pour cet agent." })}
                            </p>
                        )}
                    </div>
                ) : null}
                {fautes.length > 0 && (
                    <ul className="text-sm text-destructive" data-testid="fautes-scenarios">
                        {fautes.map((f) => (
                            <li key={f}>{f}</li>
                        ))}
                    </ul>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(false)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || brouillon === null || fautes.length > 0}>
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
