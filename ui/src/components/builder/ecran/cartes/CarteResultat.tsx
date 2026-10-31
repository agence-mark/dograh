"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the cards that show the RESULT of an action, drawn from a generic shape so they
 * follow whatever the action rendered: Prompt check, Tools, Tests, Report, Proposal for the library.
 *
 * The shape is deliberately tolerant: a list of items (`elements`, `defauts`, `resultats`, `outils`, `tests`... or the
 * first list of objects found), each with a name, a status (`statut`, `etat` or `ok`) and a message; the whole result
 * stays readable under « Raw result ». An action not available yet (`disponible: false`) is said as such, never shown
 * as done (« nothing is announced without proof »).
 *
 * Also here: the checklist line (« Tasks ») every other action of the builder leaves in the conversation.
 */
import { Check, CircleDashed, X } from "lucide-react";

import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";

import { Carte } from "./Carte";

export const TITRES_DES_CARTES: Record<string, Texte> = {
    prompt_controler: { en: "Prompt check", fr: "Contrôle du prompt" },
    outil_essayer: { en: "Tools", fr: "Outils" },
    tests_creer: { en: "Tests", fr: "Tests" },
    tests_rejouer: { en: "Tests", fr: "Tests" },
    rapport: { en: "Report", fr: "Rapport" },
    bibliotheque_proposer: { en: "Proposal for the library", fr: "Proposition pour la bibliothèque" },
};

const T = {
    pasDisponible: { en: "Not available yet: nothing is announced as done.", fr: "Pas encore disponible : rien n'est annoncé comme fait." },
    echec: { en: "The action failed:", fr: "L'action a échoué :" },
    aucun: { en: "Nothing to show.", fr: "Rien à montrer." },
    brut: { en: "Raw result", fr: "Résultat brut" },
    enCours: { en: "In progress", fr: "En cours" },
    taches: { en: "Task", fr: "Tâche" },
} satisfies Record<string, Texte>;

const CLES_DE_LISTE = ["elements", "defauts", "resultats", "outils", "tests", "items", "lignes", "scenarios"];

type Objet = Record<string, unknown>;

export interface ElementDeResultat {
    nom: string;
    statut: "ok" | "echec" | "avertissement" | "inconnu";
    message?: string;
}

const estObjet = (v: unknown): v is Objet => typeof v === "object" && v !== null && !Array.isArray(v);

function statutDe(item: Objet): ElementDeResultat["statut"] {
    const brut = String(item.statut ?? item.etat ?? item.verdict ?? "").toLowerCase();
    if (item.ok === true || ["ok", "branche", "branché", "reussi", "réussi", "passe", "vert", "valide"].includes(brut)) return "ok";
    if (item.ok === false || ["echec", "échec", "erreur", "non_branche", "non branché", "rouge", "refuse", "bloquant"].includes(brut)) return "echec";
    if (["avertissement", "warning", "attention"].includes(brut)) return "avertissement";
    return "inconnu";
}

/** The items of a result, whatever its exact shape. Pure: tested on its own. */
export function elementsDe(resultat: unknown): ElementDeResultat[] {
    if (!estObjet(resultat)) return [];
    const liste =
        CLES_DE_LISTE.map((c) => resultat[c]).find((v) => Array.isArray(v) && v.length > 0) ??
        Object.values(resultat).find((v) => Array.isArray(v) && v.length > 0 && v.every(estObjet));
    if (!Array.isArray(liste)) return [];
    return liste.map((brut, i) => {
        if (!estObjet(brut)) return { nom: String(brut), statut: "inconnu" as const };
        const nom = [brut.nom, brut.name, brut.outil, brut.regle, brut.titre, brut.test, brut.id].find((v) => typeof v === "string" && v) as string | undefined;
        const message = [brut.message, brut.detail, brut.raison, brut.erreur, brut.description].find((v) => typeof v === "string" && v) as string | undefined;
        return { nom: nom ?? `#${i + 1}`, statut: statutDe(brut), message };
    });
}

export function nonDisponible(resultat: unknown): boolean {
    return estObjet(resultat) && resultat.disponible === false;
}

const ICONE = {
    ok: <Check className="h-3.5 w-3.5 text-(--signal-ok)" aria-hidden />,
    echec: <X className="h-3.5 w-3.5 text-(--signal-danger)" aria-hidden />,
    avertissement: <CircleDashed className="h-3.5 w-3.5 text-(--signal-warn)" aria-hidden />,
    inconnu: <CircleDashed className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />,
};

export function CarteResultat({ nomDeLAction, resultat, erreur }: { nomDeLAction: string; resultat?: unknown; erreur?: boolean }) {
    const { t } = useLangue();
    const titre = TITRES_DES_CARTES[nomDeLAction] ?? { en: nomDeLAction, fr: nomDeLAction };
    const elements = elementsDe(resultat);
    return (
        <Carte type={`resultat-${nomDeLAction}`} titre={t(titre)}>
            {resultat === undefined ? (
                <p className="text-xs text-muted-foreground">{t(T.enCours)}</p>
            ) : nonDisponible(resultat) ? (
                <p className="text-xs text-muted-foreground" data-non-disponible>
                    {t(T.pasDisponible)}
                </p>
            ) : erreur && elements.length === 0 ? (
                <p className="text-xs text-destructive">
                    {t(T.echec)} {String((resultat as Objet)?.erreur ?? "")}
                </p>
            ) : elements.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t(T.aucun)}</p>
            ) : (
                <ul className="space-y-1">
                    {elements.map((e, i) => (
                        <li key={`${e.nom}-${i}`} className="flex items-start gap-2 text-xs" data-statut={e.statut}>
                            <span className="mt-0.5 shrink-0">{ICONE[e.statut]}</span>
                            <span>
                                <b>{e.nom}</b>
                                {e.message ? ` : ${e.message}` : ""}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
            {resultat !== undefined && (
                <details className="mt-2 text-xs text-muted-foreground">
                    <summary>{t(T.brut)}</summary>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-2">{JSON.stringify(resultat, null, 2)}</pre>
                </details>
            )}
        </Carte>
    );
}

/** A line of the checklist: one per action of the builder that has no card of its own. */
export function LigneDeTache({ nom, termine, erreur }: { nom: string; termine: boolean; erreur: boolean }) {
    const { t } = useLangue();
    return (
        <div className="my-1 flex items-center gap-2 text-xs text-muted-foreground" data-tache={nom} data-etat={erreur ? "echec" : termine ? "fait" : "en-cours"} title={t(T.taches)}>
            {erreur ? <X className="h-3.5 w-3.5 text-(--signal-danger)" aria-hidden /> : termine ? <Check className="h-3.5 w-3.5 text-(--signal-ok)" aria-hidden /> : <CircleDashed className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            <span>{nom}</span>
        </div>
    );
}
