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
import { useState } from "react";

import { lancerLEssaiDUnOutilApiV1BuilderOutilsEssaiPost } from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

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
    essaiTitre: { en: "Trial to validate", fr: "Essai à valider" },
    essaiAide: {
        en: "This tool writes at the client's. Nothing was called: a person runs the trial, with fictitious data only.",
        fr: "Cet outil écrit chez le client. Rien n'a été appelé : une personne lance l'essai, avec des données fictives seulement.",
    },
    essaiOutil: { en: "Tool", fr: "Outil" },
    essaiMethode: { en: "Method", fr: "Méthode" },
    essaiAdresse: { en: "Address", fr: "Adresse" },
    essaiDonnees: { en: "Test data", fr: "Données de test" },
    lancer: { en: "Run the trial", fr: "Lancer l'essai" },
    enEssai: { en: "Trial running...", fr: "Essai en cours..." },
    branche: { en: "Connected: the system answered with a valid answer.", fr: "Branché : le système a répondu une réponse valide." },
    nonBranche: { en: "Not connected:", fr: "Non branché :" },
    essaiEchec: { en: "The trial could not run.", fr: "L'essai n'a pas pu partir." },
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

/** The « trial to validate » shape the server renders for a tool that writes at the client's (review R5). */
export function essaiAValider(resultat: unknown): { outil: string; methode: string; adresse: string; donnees: Objet } | null {
    if (!estObjet(resultat) || resultat.a_valider !== true) return null;
    return {
        outil: String(resultat.outil ?? ""),
        methode: String(resultat.methode ?? ""),
        adresse: String(resultat.adresse ?? ""),
        donnees: estObjet(resultat.donnees_test) ? resultat.donnees_test : {},
    };
}

/** The person's gesture: runs the trial through its own route (the builder has no way to). */
function EssaiAValider({ essai, workflowId }: { essai: NonNullable<ReturnType<typeof essaiAValider>>; workflowId?: number }) {
    const { t } = useLangue();
    const [etat, setEtat] = useState<"attente" | "en-cours" | "fait">("attente");
    const [verdict, setVerdict] = useState<{ branche: boolean; raison: string } | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const lancer = async () => {
        if (workflowId === undefined) return;
        setEtat("en-cours");
        setErreur(null);
        const reponse = await lancerLEssaiDUnOutilApiV1BuilderOutilsEssaiPost({
            body: { workflow_id: workflowId, outil: essai.outil, donnees_test: essai.donnees },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, t(T.essaiEchec)));
            setEtat("attente");
            return;
        }
        const donnees = (reponse.data ?? {}) as Objet;
        setVerdict({ branche: donnees.branche === true, raison: String(donnees.raison ?? "") });
        setEtat("fait");
    };

    return (
        <div data-essai-a-valider={essai.outil} className="mb-2 rounded-md border border-dashed p-2 text-xs">
            <p className="mb-1 font-semibold">{t(T.essaiTitre)}</p>
            <p className="mb-1 text-muted-foreground">{t(T.essaiAide)}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                <dt className="text-muted-foreground">{t(T.essaiOutil)}</dt>
                <dd>{essai.outil}</dd>
                <dt className="text-muted-foreground">{t(T.essaiMethode)}</dt>
                <dd>{essai.methode}</dd>
                <dt className="text-muted-foreground">{t(T.essaiAdresse)}</dt>
                <dd className="break-all">{essai.adresse}</dd>
                <dt className="text-muted-foreground">{t(T.essaiDonnees)}</dt>
                <dd>
                    <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-1">{JSON.stringify(essai.donnees, null, 2)}</pre>
                </dd>
            </dl>
            {etat !== "fait" ? (
                <Button type="button" size="sm" className="mt-2" disabled={etat === "en-cours" || workflowId === undefined} onClick={() => void lancer()}>
                    {etat === "en-cours" ? t(T.enEssai) : t(T.lancer)}
                </Button>
            ) : (
                <p className="mt-2" data-verdict-essai={verdict?.branche ? "branche" : "non-branche"}>
                    {verdict?.branche ? t(T.branche) : `${t(T.nonBranche)} ${verdict?.raison ?? ""}`}
                </p>
            )}
            {erreur && <p role="alert" className="mt-1 text-destructive">{erreur}</p>}
        </div>
    );
}

export function CarteResultat({
    nomDeLAction,
    resultat,
    erreur,
    workflowId,
}: {
    nomDeLAction: string;
    resultat?: unknown;
    erreur?: boolean;
    workflowId?: number;
}) {
    const { t } = useLangue();
    const titre = TITRES_DES_CARTES[nomDeLAction] ?? { en: nomDeLAction, fr: nomDeLAction };
    const elements = elementsDe(resultat);
    const essai = essaiAValider(resultat);
    return (
        <Carte type={`resultat-${nomDeLAction}`} titre={t(titre)}>
            {essai && <EssaiAValider essai={essai} workflowId={workflowId} />}
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
