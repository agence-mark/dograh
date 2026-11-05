"use client";

/**
 * [.mark] Builder partie 3, SA-L3a (décisions 05 § 11 et § 14) : la liste « Prêt à publier », UNE seule, la même dans la carte des
 * Réglages et dans la fenêtre « Publier ». Quatre états (fait, à faire, bloquant, hérité) ; ce qui manque est écrit en clair ;
 * « Régler » mène à l'endroit exact ; les lignes faites sont repliées, les obligatoires en tête ; un réglage « sans effet » propose
 * sa correction en un clic. Forme de la maquette (`components/studio/liste-pret.tsx`).
 */
import { ChevronDown, Circle, CircleAlert, CircleCheck, CornerLeftUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet } from "@/client/sdk.gen";
import type { EtapeDePreparation } from "@/client/types.gen";
import { useBuilderEcran } from "@/components/builder/ecran/store";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../../langue/langue";
import { Info } from "../../studio/marques";
import { useRecalculDuPret } from "./recalcul";
import { type CorrectionDeLigne, TEXTES_DES_CONSTATS, TEXTES_DES_CORRECTIONS, TITRES_DES_LIGNES } from "./textes";

export type LigneDePret = EtapeDePreparation;

/** Les textes des huit lignes de la préparation (le serveur ne donne que l'identifiant). */
export type TextesDesEtapes = Record<string, { titre: Texte; source: Texte }>;

/** La lecture de la liste, recalculée à chaque enregistrement (Réglages, builder, correction). */
export function useListeDePret(workflowId: number, aussi?: unknown) {
    const [lignes, setLignes] = useState<LigneDePret[] | null>(null);
    const [echec, setEchec] = useState(false);
    const recalcul = useRecalculDuPret((s) => s.n);
    // Un geste du builder (une opération du brouillon) change l'agent : on relit.
    const gestes = useBuilderEcran((s) => s.operationsVives.length);

    const lire = useCallback(async () => {
        try {
            const reponse = await lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet({ path: { workflow_id: workflowId } });
            if (reponse.error || !reponse.data) setEchec(true);
            else {
                setEchec(false);
                setLignes(reponse.data.etapes);
            }
        } catch {
            setEchec(true);
        }
    }, [workflowId]);

    useEffect(() => {
        void lire();
    }, [lire, recalcul, gestes, aussi]);

    return { lignes, echec, relire: lire };
}

const estAFaire = (l: LigneDePret) => l.etat === "a_faire" || l.etat === "bloquant";

function Icone({ ligne }: { ligne: LigneDePret }) {
    if (ligne.etat === "fait") return <CircleCheck data-cercle="fait" className="size-4 shrink-0 text-(--point-fini)" />;
    if (ligne.etat === "herite") return <CornerLeftUp data-cercle="herite" className="size-4 shrink-0 text-muted-foreground" />;
    if (ligne.etat === "bloquant") return <CircleAlert data-cercle="bloquant" className="size-4 shrink-0 text-destructive" />;
    return (
        <Circle
            data-cercle={ligne.niveau === "requis" ? "requis" : "conseille"}
            className={cn("size-4 shrink-0", ligne.niveau === "requis" ? "text-destructive" : "text-(--acc)")}
        />
    );
}

export function Anneau({ faites, total, bloque }: { faites: number; total: number; bloque: boolean }) {
    const { t } = useLangue();
    const rayon = 52;
    const tour = 2 * Math.PI * rayon;
    return (
        <div className="relative mx-auto size-[120px]" role="img" aria-label={`${faites}/${total}`}>
            <svg width="120" height="120" className="-rotate-90">
                <circle cx="60" cy="60" r={rayon} fill="none" stroke="currentColor" className="text-foreground/10" strokeWidth="8" />
                <circle
                    cx="60"
                    cy="60"
                    r={rayon}
                    fill="none"
                    stroke="currentColor"
                    className={bloque ? "text-destructive" : "text-foreground"}
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={tour}
                    strokeDashoffset={tour * (1 - (total === 0 ? 0 : faites / total))}
                />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-semibold tabular-nums">
                    {faites}/{total}
                </span>
                <span className="text-[11px] text-muted-foreground">{t({ en: "ready", fr: "prêt" })}</span>
            </div>
        </div>
    );
}

function Rangee({
    ligne,
    textesDesEtapes,
    regler,
    corriger,
    enCours,
}: {
    ligne: LigneDePret;
    textesDesEtapes: TextesDesEtapes;
    regler: (l: LigneDePret) => void;
    corriger?: (l: LigneDePret, c: CorrectionDeLigne) => void;
    enCours: boolean;
}) {
    const { t } = useLangue();
    const constat = ligne.constat ? TEXTES_DES_CONSTATS[ligne.constat] : undefined;
    const textes = constat ? { titre: constat.titre, source: constat.info } : (textesDesEtapes[ligne.id] ?? TITRES_DES_LIGNES[ligne.id]);
    if (!textes) return null;
    const reste = estAFaire(ligne);
    const requis = ligne.niveau === "requis";
    const noms = ligne.noms ?? [];
    const manque = !reste
        ? ligne.etat === "herite"
            ? t({ en: "inherited from the main agent", fr: "hérité du principal" })
            : ""
        : constat
          ? t(constat.detail(noms))
          : (ligne.manquants ?? []).join(", ");
    const corrections = (ligne.corrections ?? []) as unknown as CorrectionDeLigne[];
    return (
        <li data-etape={ligne.id} data-etat={ligne.etat} className="flex items-start gap-3 py-2.5">
            <span className="mt-0.5">
                <Icone ligne={ligne} />
            </span>
            <div className="min-w-0 flex-1">
                <button
                    type="button"
                    onClick={() => regler(ligne)}
                    className="flex w-full cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 text-left text-sm hover:font-semibold"
                >
                    <span className={cn(reste ? "font-medium" : "text-muted-foreground")}>{t(textes.titre)}</span>
                    {!requis && <span className="text-[11px] font-normal text-muted-foreground">{t({ en: "advised", fr: "conseillé" })}</span>}
                    <Info>{t(textes.source)}</Info>
                </button>
                {manque && <p className="text-xs text-muted-foreground">{manque}</p>}
                {reste && corrections.length > 0 && corriger && (
                    <div className="mt-1.5 flex flex-wrap gap-2">
                        {corrections.map((c, i) => {
                            const texte = TEXTES_DES_CORRECTIONS[c.id]?.(c);
                            if (!texte) return null;
                            return (
                                <Button
                                    key={`${c.id}-${c.noeud_id ?? ""}-${c.liaison_id ?? ""}-${i}`}
                                    size="sm"
                                    variant={i === 0 ? "default" : "outline"}
                                    className="h-7"
                                    disabled={enCours}
                                    data-correction={c.id}
                                    onClick={() => corriger(ligne, c)}
                                >
                                    {t(texte)}
                                </Button>
                            );
                        })}
                    </div>
                )}
            </div>
            {ligne.etat === "bloquant" && (
                <span className="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium text-destructive">{t({ en: "Blocks", fr: "Bloque" })}</span>
            )}
            {reste && (
                <Button variant="outline" size="sm" className="h-7 shrink-0" onClick={() => regler(ligne)}>
                    {t({ en: "Fix", fr: "Régler" })}
                </Button>
            )}
        </li>
    );
}

/**
 * `regler` mène à l'endroit exact de la ligne (le parent sait comment : thème de la page, étape du graphe, onglet) ; `corriger`
 * joue la correction en un clic (absent : la ligne ne propose que « Régler »). Les lignes faites sont repliées.
 */
export function ListePret({
    lignes,
    textesDesEtapes,
    regler,
    corriger,
    enCours = false,
    avecAnneau = false,
}: {
    lignes: LigneDePret[];
    textesDesEtapes: TextesDesEtapes;
    regler: (l: LigneDePret) => void;
    corriger?: (l: LigneDePret, c: CorrectionDeLigne) => void;
    enCours?: boolean;
    avecAnneau?: boolean;
}) {
    const { t } = useLangue();
    const [faitesOuvertes, setFaitesOuvertes] = useState(false);
    const visibles = lignes.filter((l) => l.etat !== "sans_objet");
    const reste = visibles.filter(estAFaire);
    const faites = visibles.filter((l) => !estAFaire(l));
    const bloquantes = reste.filter((l) => l.etat === "bloquant").length;
    const requisesRestantes = reste.filter((l) => l.niveau === "requis").length;
    const rangee = (l: LigneDePret) => (
        <Rangee key={l.id} ligne={l} textesDesEtapes={textesDesEtapes} regler={regler} corriger={corriger} enCours={enCours} />
    );
    const corps = (
        <div className="min-w-0 flex-1">
            <p className="pb-1 text-sm text-muted-foreground" data-preparation="resume">
                {reste.length === 0
                    ? t({ en: "All set: the agent can be published.", fr: "Tout est prêt : l'agent peut être publié." })
                    : bloquantes > 0
                      ? t({
                            en: `${bloquantes} check${bloquantes > 1 ? "s" : ""} block${bloquantes > 1 ? "" : "s"} the publication.`,
                            fr: `${bloquantes} contrôle${bloquantes > 1 ? "s" : ""} bloque${bloquantes > 1 ? "nt" : ""} la publication.`,
                        })
                      : t({
                            en: `${reste.length} thing${reste.length > 1 ? "s" : ""} to look at before publishing.`,
                            fr: `${reste.length} chose${reste.length > 1 ? "s" : ""} à voir avant de publier.`,
                        })}
            </p>
            <span className="sr-only" data-preparation="restantes">
                {requisesRestantes === 0
                    ? t({ en: "Nothing required is missing", fr: "Rien d'obligatoire ne manque" })
                    : t({ en: `${requisesRestantes} required to do`, fr: `${requisesRestantes} obligatoire${requisesRestantes > 1 ? "s" : ""} à faire` })}
            </span>
            <ul className="divide-y">{reste.map(rangee)}</ul>
            {faites.length > 0 && (
                <div className={reste.length ? "border-t" : ""}>
                    <button
                        type="button"
                        data-preparation="faites"
                        onClick={() => setFaitesOuvertes(!faitesOuvertes)}
                        aria-expanded={faitesOuvertes}
                        className="flex w-full cursor-pointer items-center gap-2 py-2.5 text-sm text-muted-foreground hover:font-semibold"
                    >
                        <ChevronDown className={cn("size-4 transition-transform", !faitesOuvertes && "-rotate-90")} />
                        {t({ en: `${faites.length} done`, fr: `${faites.length} faite${faites.length > 1 ? "s" : ""}` })}
                    </button>
                    {faitesOuvertes && <ul className="divide-y">{faites.map(rangee)}</ul>}
                </div>
            )}
        </div>
    );
    if (!avecAnneau) return corps;
    return (
        <section
            aria-label={t({ en: "Ready to publish", fr: "Prêt à publier" })}
            data-preparation="liste"
            className="grid items-start gap-6 rounded-2xl border bg-card p-6 md:grid-cols-[180px_1fr]"
        >
            <div className="space-y-2 pt-2">
                <Anneau faites={faites.length} total={visibles.length} bloque={bloquantes > 0} />
                <p className="text-center text-xs text-muted-foreground">{t({ en: "Ready to publish", fr: "Prêt à publier" })}</p>
            </div>
            {corps}
        </section>
    );
}
