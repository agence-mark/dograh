"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.11, maquette section 8) : la section « Phrases fixes à cette étape » de la
 * fenêtre d'une étape de l'éditeur. Elle liste les règles propres à l'étape (une carte chacune, comme dans le thème
 * Phrases), rappelle celles qui valent quand même ici (agent, groupe), et « Ajouter à cette étape » ouvre la MÊME modale
 * que le thème, l'endroit déjà choisi. Un seul stockage : la clé `phrases_regles` de l'agent ; chaque geste de la
 * modale s'enregistre tout de suite (la fenêtre d'une étape n'a pas de bouton de thème).
 */
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ReglePhrase } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { useLangue } from "../langue/langue";
import { CartePhrase } from "../reglages-agent/phrases/CartePhrase";
import { useEnvironnementPhrases } from "../reglages-agent/phrases/environnement";
import { ModaleAjout } from "../reglages-agent/phrases/ModaleAjout";
import { ModaleRegle } from "../reglages-agent/phrases/ModaleRegle";
import {
    chargeRegle,
    cleDeRegle,
    erreursDesPhrases,
    etapeDeLaRegle,
    motifDe,
    normaliserRegle,
    origineDe,
    ORIGINES,
} from "../reglages-agent/phrases/modele";

export const ID_SECTION_PHRASES_ETAPE = "phrases_de_l_etape";

export const PhrasesDeLEtape = ({ etapeId, etapeNom }: { etapeId: string; etapeNom: string }) => {
    const { t } = useLangue();
    const contexte = useWorkflowOptional();
    const phrases = contexte?.phrasesDeLEtape;
    const configuration = phrases?.configuration ?? null;
    const etapes = useMemo(() => {
        // Le nom que l'on tape dans la fenêtre vaut tout de suite pour cette étape.
        const liste = phrases?.etapes ?? [];
        return liste.some((e) => e.id === etapeId) ? liste.map((e) => (e.id === etapeId ? { ...e, nom: etapeNom || e.nom } : e)) : [...liste, { id: etapeId, nom: etapeNom }];
    }, [phrases?.etapes, etapeId, etapeNom]);
    const { env, contexte: ctx } = useEnvironnementPhrases({
        configuration,
        etapes,
        outilsUuids: phrases?.outilsUuids ?? [],
        actif: phrases !== undefined,
        peutGroupe: phrases?.peutGroupe ?? false,
        workflowId: contexte?.workflowId,
    });
    const [ouverte, setOuverte] = useState<number | null>(null);
    const [ajout, setAjout] = useState(false);
    if (!phrases) return null;

    const regles = (configuration?.phrases_regles ?? []).map(normaliserRegle);
    const deLEtape = regles.map((r, index) => ({ r, index })).filter(({ r }) => r.portee === "etape" && etapeDeLaRegle(r, etapes)?.id === etapeId);
    const vautAussiIci = regles.filter((r) => r.portee !== "etape" && r.active !== false && !deLEtape.some(({ r: e }) => e.motif === r.motif));

    const enregistrer = async (suivantes: ReglePhrase[]) => {
        const erreurs = erreursDesPhrases(suivantes, etapes);
        if (erreurs.length > 0) {
            toast.error(t(erreurs[0].message));
            return false;
        }
        try {
            await phrases.enregistrer(suivantes.map((r) => chargeRegle(r, etapes)));
            toast.success(t({ en: "Phrases saved.", fr: "Phrases enregistrées." }));
            return true;
        } catch {
            toast.error(t({ en: "The phrases could not be saved.", fr: "Les phrases n'ont pas pu être enregistrées." }));
            return false;
        }
    };

    return (
        <ChampReglage
            cle={ID_SECTION_PHRASES_ETAPE}
            libelle={{ en: "Fixed sentences at this step", fr: "Phrases fixes à cette étape" }}
            aides={[
                {
                    en: "Those that apply here: the step's own, then the agent's and the group's. Same dialog as the Phrases theme of the agent's settings.",
                    fr: "Celles qui valent ici : propres à l'étape, puis celles de l'agent et du groupe. Même fenêtre de réglage que le thème Phrases des réglages de l'agent.",
                },
            ]}
        >
            <div className="space-y-3" data-section-phrases-etape>
                <div className="flex justify-end">
                    <Button size="sm" variant="outline" onClick={() => setAjout(true)}>
                        <Plus className="h-3.5 w-3.5" /> {t({ en: "Add to this step", fr: "Ajouter à cette étape" })}
                    </Button>
                </div>
                {deLEtape.length === 0 && (
                    <p className="text-xs text-muted-foreground">{t({ en: "No sentence of its own at this step.", fr: "Aucune phrase propre à cette étape." })}</p>
                )}
                {deLEtape.map(({ r, index }) => {
                    const motif = motifDe(r.motif);
                    if (!motif) return null;
                    return (
                        <CartePhrase
                            key={cleDeRegle(r)}
                            id={cleDeRegle(r)}
                            regle={r}
                            motif={motif}
                            origine={origineDe(r)}
                            contexte={ctx}
                            etape={etapeNom}
                            active={r.active !== false}
                            derniere=""
                            onOuvrir={() => setOuverte(index)}
                            onBasculer={(active) => void enregistrer(regles.map((x, i) => (i === index ? { ...x, active } : x)))}
                        />
                    );
                })}
                {vautAussiIci.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-vaut-aussi-ici>
                        {t({ en: "Also apply here, with no step rule:", fr: "Valent aussi ici, sans règle d'étape :" })}
                        {vautAussiIci.map((r) => (
                            <Badge key={cleDeRegle(r)} variant="outline" className="font-normal">
                                {t(motifDe(r.motif)?.libelle ?? { en: r.motif, fr: r.motif })} · {t(ORIGINES[origineDe(r)])}
                            </Badge>
                        ))}
                    </div>
                )}
            </div>
            {ouverte !== null && regles[ouverte] && (
                <ModaleRegle
                    key={`regle-${ouverte}`}
                    regle={regles[ouverte]}
                    env={env}
                    peutSupprimer
                    onEnregistrer={async (r) => {
                        if (await enregistrer(regles.map((x, i) => (i === ouverte ? r : x)))) setOuverte(null);
                    }}
                    onSupprimer={async () => {
                        if (await enregistrer(regles.filter((_, i) => i !== ouverte))) setOuverte(null);
                    }}
                    onFermer={() => setOuverte(null)}
                />
            )}
            {ajout && (
                <ModaleAjout
                    env={env}
                    endroitInitial={{ portee: "etape", etape: { id: etapeId, nom: etapeNom } }}
                    reglesExistantes={regles}
                    onAjouter={async (r) => {
                        if (await enregistrer([...regles, r])) setAjout(false);
                    }}
                    onFermer={() => setAjout(false)}
                />
            )}
        </ChampReglage>
    );
};
