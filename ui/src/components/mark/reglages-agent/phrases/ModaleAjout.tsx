"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.7, 4.11) : « Ajouter une phrase », en DEUX étapes.
 * 1) choisir l'endroit et le moment : une carte par motif du catalogue, rangée par moment, avec ce qu'elle
 *    permet et le nombre de règles déjà réglées ;
 * 2) le formulaire de la règle, pré-rempli des valeurs du catalogue, avec « Changer de motif ».
 * Trois entrées, une seule fenêtre : le thème, la vue du groupe (l'endroit est déjà choisi) et la fenêtre d'une
 * étape du parcours (idem, avec l'étape).
 */
import { AlertTriangle, ChevronRight, Clock, Info, LogOut, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ReglePhrase } from "@/types/workflow-configurations";

import { useLangue } from "../../langue/langue";
import { CadreModale, L } from "./cadre";
import { iconeDuMotif,TONS } from "./CartePhrase";
import { type EnvironnementPhrases, ModaleRegle } from "./ModaleRegle";
import {
    appliquerEndroit,
    type Endroit,
    type Moment,
    MOMENTS,
    type MotifDePhrase,
    MOTIFS_DE_PHRASES,
    regleNeuve,
    valeurEndroit,
} from "./modele";

const MOMENT_TITRES: Record<Moment, { titre: { en: string; fr: string }; aide: { en: string; fr: string } }> = {
    attente: {
        titre: { en: "During a wait", fr: "Pendant une attente" },
        aide: { en: "Triggered by time passing: a delay, repeats.", fr: "Déclenchées par le temps qui passe : un délai, des redites." },
    },
    probleme: {
        titre: { en: "After a problem", fr: "Après un problème" },
        aide: { en: "Triggered by a fact: no delay, a cap of incidents in the call, then the exit.", fr: "Déclenchées par un fait : pas de délai, un plafond d'incidents dans l'appel, puis la sortie." },
    },
    action: {
        titre: { en: "Before an action", fr: "Avant une action" },
        aide: { en: "Said right before the code acts.", fr: "Dite juste avant que le code agisse." },
    },
};

export const ModaleAjout = ({
    env,
    endroitInitial,
    motifInitial,
    reglesExistantes,
    onAjouter,
    onFermer,
}: {
    env: EnvironnementPhrases;
    /** Où la règle sera posée au départ (la vue du groupe et la fenêtre d'une étape le fixent d'avance). */
    endroitInitial: Endroit;
    motifInitial?: string | null;
    reglesExistantes: ReglePhrase[];
    onAjouter: (r: ReglePhrase) => void;
    onFermer: () => void;
}) => {
    const { t } = useLangue();
    const [endroit, setEndroit] = useState<string>(valeurEndroit(regleNeuve(MOTIFS_DE_PHRASES[0], endroitInitial), env.etapes));
    const [choisi, setChoisi] = useState<MotifDePhrase | null>(MOTIFS_DE_PHRASES.find((m) => m.id === motifInitial) ?? null);
    const [regle, setRegle] = useState<ReglePhrase | null>(null);

    const nouvelleRegle = (motif: MotifDePhrase): ReglePhrase =>
        appliquerEndroit(regleNeuve(motif, { portee: "agent" }), endroit, env.etapes);

    if (choisi) {
        const depart = regle ?? nouvelleRegle(choisi);
        return (
            <ModaleRegle
                regle={depart}
                env={env}
                nouvelle
                existeUneRegleDuGroupe={depart.portee !== "groupe" && reglesExistantes.some((r) => r.motif === choisi.id && r.portee === "groupe")}
                onEnregistrer={onAjouter}
                onFermer={onFermer}
                onRetour={() => {
                    setRegle(null);
                    setChoisi(null);
                }}
            />
        );
    }
    return (
        <CadreModale
            identifiant="ajout-etape-1"
            titre={t({ en: "Add a fixed sentence", fr: "Ajouter une phrase fixe" })}
            description={t({
                en: "Step 1 of 2: choose when the voice speaks. The form then opens with proposed values.",
                fr: "Étape 1 sur 2 : choisissez le moment où la voix parle. Le formulaire s'ouvre ensuite avec des valeurs proposées.",
            })}
            onFermer={onFermer}
            pied={
                <>
                    <span className="text-xs text-muted-foreground">{t({ en: "Step 1 of 2", fr: "Étape 1 sur 2" })}</span>
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                </>
            }
        >
            <div className="space-y-5">
                <L label={t({ en: "In", fr: "Dans" })} nom="dans-ajout" aide={t({ en: "You can still change it at the next step.", fr: "Modifiable à l'étape suivante." })}>
                    <Select value={endroit} onValueChange={setEndroit}>
                        <SelectTrigger id="ajout_endroit" aria-label={t({ en: "In", fr: "Dans" })} className="w-72">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {env.peutGroupe && <SelectItem value="groupe">{t({ en: "The whole group", fr: "Tout le groupe" })}</SelectItem>}
                            <SelectItem value="agent">{t({ en: "This agent", fr: "Cet agent" })}</SelectItem>
                            {env.etapes.map((e) => (
                                <SelectItem key={e.id} value={`etape:${e.id}`}>
                                    {`${t({ en: "Step", fr: "Étape" })} : ${e.nom}`}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </L>
                <p className="text-sm font-medium">{t({ en: "When should the voice speak?", fr: "Quand la voix doit-elle parler ?" })}</p>
                {MOMENTS.map((moment) => (
                    <div key={moment} className="space-y-2">
                        <div>
                            <h4 className="text-sm font-semibold">{t(MOMENT_TITRES[moment].titre)}</h4>
                            <p className="text-xs text-muted-foreground">{t(MOMENT_TITRES[moment].aide)}</p>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                            {MOTIFS_DE_PHRASES.filter((m) => m.moment === moment).map((motif) => {
                                const Icone = iconeDuMotif(motif);
                                const existantes = reglesExistantes.filter((r) => r.motif === motif.id).length;
                                return (
                                    <button
                                        key={motif.id}
                                        type="button"
                                        data-motif-ajout={motif.id}
                                        aria-label={t(motif.libelle)}
                                        onClick={() => setChoisi(motif)}
                                        className="group flex items-start gap-3 rounded-lg border bg-card p-3 text-left transition hover:border-foreground/30 hover:shadow-sm"
                                    >
                                        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${TONS[motif.moment]}`}>
                                            <Icone className="h-4 w-4" />
                                        </span>
                                        <span className="min-w-0 flex-1 space-y-1">
                                            <span className="flex items-center justify-between gap-2">
                                                <span className="text-sm font-semibold">{t(motif.libelle)}</span>
                                                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5" />
                                            </span>
                                            <span className="block text-xs text-muted-foreground">{t(motif.quand)}</span>
                                            <span className="flex flex-wrap gap-1 pt-0.5">
                                                {motif.filtre_outil && (
                                                    <span className="inline-flex items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 text-[11px]">
                                                        <Wrench className="h-3 w-3" />
                                                        {t({ en: "a specific tool possible", fr: "un outil précis possible" })}
                                                    </span>
                                                )}
                                                <span className="inline-flex items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 text-[11px]">
                                                    {motif.moment === "attente" ? <Clock className="h-3 w-3" /> : motif.moment === "probleme" ? <AlertTriangle className="h-3 w-3" /> : <LogOut className="h-3 w-3" />}
                                                    {!motif.a_un_delai && motif.moment === "attente"
                                                        ? t({ en: "the guard's delay, once", fr: "délai de la garde, une fois" })
                                                        : motif.moment === "attente"
                                                          ? t({ en: "delay and repeats", fr: "délai et redites" })
                                                          : motif.moment === "probleme"
                                                            ? t({ en: "cap, then exit", fr: "plafond puis sortie" })
                                                            : t({ en: "before the action", fr: "avant l'action" })}
                                                </span>
                                                {existantes > 0 && (
                                                    <span className="inline-flex items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground">
                                                        <Info className="h-3 w-3" />
                                                        {t({ en: `${existantes} already set`, fr: `${existantes} déjà réglée${existantes > 1 ? "s" : ""}` })}
                                                    </span>
                                                )}
                                            </span>
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </CadreModale>
    );
};
