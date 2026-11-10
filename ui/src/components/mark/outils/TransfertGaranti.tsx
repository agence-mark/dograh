"use client";

/**
 * [.mark] Clôture D2 (D14, Evan 09/11) : « Transfert garanti à l'arrivée » vit sur la fenêtre de l'OUTIL DE TRANSFERT D'APPEL, là où il
 * sert, et nulle part ailleurs (il a quitté le thème « Données de l'appel » des réglages de l'agent : un seul endroit).
 *
 * C'est un réglage DE L'AGENT (`transfert_garanti`) : quand l'agent arrive dans une étape qui porte cet outil et que l'entreprise est
 * ouverte, le code lance lui-même le transfert. Un outil est partagé entre agents : le bloc liste donc les agents qui l'utilisent (une
 * seule lecture des statistiques de l'outil, les réglages de ces agents lus ensemble) et porte un interrupteur par agent. Un seul
 * « Enregistrer » : le pied de la fenêtre enregistre l'outil puis ces réglages (`annexe`), et « Annuler » ou quitter prévient pour les deux.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getWorkflowApiV1WorkflowFetchWorkflowIdGet, statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet, updateWorkflowApiV1WorkflowWorkflowIdPut } from "@/client/sdk.gen";
import { Switch } from "@/components/ui/switch";

import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { EtatVide } from "../studio/etat-vide";
import { Info } from "../studio/marques";

export type AnnexeDeLOutil = {
    modifie: boolean;
    /** Enregistre les réglages des agents ; `false` : au moins un n'est pas enregistré (la notification d'échec est déjà dite). */
    enregistrer: () => Promise<boolean>;
};

type Ligne = { id: number; nom: string; etapes: string[]; valeur: boolean; sansEffet: boolean; configuration: Record<string, unknown> };

const T = {
    titre: { en: "Guaranteed transfer on arrival", fr: "Transfert garanti à l'arrivée" },
    info: {
        en: "When the agent arrives in a step that carries this call transfer tool and the business is open (its opening hours), the code launches the transfer itself once the step's first reply has been said in full. Off, the model decides whether to call it. A setting of each agent, not of the tool alone.",
        fr: "Quand l'agent arrive dans une étape qui porte cet outil de transfert d'appel et que l'entreprise est ouverte (ses horaires d'ouverture), le code lance lui-même le transfert une fois la première réplique de l'étape dite en entier. Éteint, c'est le modèle qui décide de l'appeler. Un réglage de chaque agent, pas de l'outil seul.",
    },
    aucun: { en: "No agent uses this tool yet.", fr: "Aucun agent n'utilise encore cet outil." },
    sansEffet: { en: "No effect: this agent does not take notes", fr: "Sans effet : cet agent ne prend pas de notes" },
    defaut: { en: "Default: off", fr: "Par défaut : éteint" },
    echec: {
        en: "Guaranteed transfer not saved. If the live version of an agent is protected, use a branch.",
        fr: "Transfert garanti non enregistré. Si la version en ligne d'un agent est protégée, passez par une branche.",
    },
} satisfies Record<string, Texte>;

export function TransfertGaranti({ toolUuid, inscrire }: { toolUuid: string; inscrire: (a: AnnexeDeLOutil | null) => void }) {
    const { t } = useLangue();
    const [lignes, setLignes] = useState<Ligne[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [choix, setChoix] = useState<Record<number, boolean>>({});

    const lire = useCallback(async () => {
        const stats = await statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet({ path: { tool_uuid: toolUuid }, query: { page: 0 } });
        if (stats.error || !stats.data) return setErreur(true);
        // Les réglages des agents se lisent ensemble, jamais l'un après l'autre.
        const lues = await Promise.all(
            stats.data.agents.map(async (a) => {
                const r = await getWorkflowApiV1WorkflowFetchWorkflowIdGet({ path: { workflow_id: a.agent_id } });
                return { a, r };
            }),
        );
        if (lues.some(({ r }) => r.error || !r.data)) return setErreur(true);
        setErreur(false);
        const suite = lues.map(({ a, r }): Ligne => {
            const configuration = ((r.data as { workflow_configurations?: Record<string, unknown> }).workflow_configurations ?? {}) as Record<string, unknown>;
            return {
                id: a.agent_id,
                nom: a.agent,
                etapes: a.etapes,
                valeur: configuration.transfert_garanti === true,
                sansEffet: configuration.fiche_au_fil_de_leau !== true,
                configuration,
            };
        });
        setLignes(suite);
        setChoix(Object.fromEntries(suite.map((l) => [l.id, l.valeur])));
    }, [toolUuid]);

    useEffect(() => {
        void lire();
    }, [lire]);

    const modifies = useMemo(() => (lignes ?? []).filter((l) => choix[l.id] !== undefined && choix[l.id] !== l.valeur), [lignes, choix]);
    const derniers = useRef({ modifies, choix });
    derniers.current = { modifies, choix };

    const enregistrer = useCallback(async (): Promise<boolean> => {
        const { modifies: aEcrire, choix: valeurs } = derniers.current;
        let tout = true;
        for (const l of aEcrire) {
            const r = await updateWorkflowApiV1WorkflowWorkflowIdPut({
                path: { workflow_id: l.id },
                body: { name: l.nom, workflow_definition: null, workflow_configurations: { ...l.configuration, transfert_garanti: valeurs[l.id] } },
            });
            if (r.error) {
                tout = false;
                notifier.echec(T.echec, { erreur: r.error });
            }
        }
        if (tout) await lire();
        return tout;
    }, [lire]);

    const modifie = modifies.length > 0;
    useEffect(() => {
        inscrire({ modifie, enregistrer });
    }, [inscrire, modifie, enregistrer]);
    useEffect(() => () => inscrire(null), [inscrire]);

    return (
        <section className="space-y-2 pt-6" data-bloc="transfert-garanti" aria-label={t(T.titre)}>
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
                {t(T.titre)}
                <Info>{t(T.info)}</Info>
            </h3>
            {erreur ? (
                <EtatVide cas="erreur" compact reessayer={() => void lire()} />
            ) : lignes === null ? (
                <EtatVide cas="chargement" lignes={2} />
            ) : lignes.length === 0 ? (
                <p className="py-2 text-sm text-muted-foreground">{t(T.aucun)}</p>
            ) : (
                <div className="divide-y">
                    {lignes.map((l) => (
                        <label key={l.id} className="flex cursor-pointer items-center gap-4 py-3" data-agent={l.id}>
                            <span className="min-w-0 flex-1">
                                <span className="block text-sm font-medium">{l.nom}</span>
                                <span className="block text-xs text-muted-foreground">
                                    {l.etapes.join(" · ")}
                                    {l.sansEffet ? ` · ${t(T.sansEffet)}` : ` · ${t(T.defaut)}`}
                                </span>
                            </span>
                            <Switch
                                checked={choix[l.id] ?? l.valeur}
                                onCheckedChange={(v) => setChoix((x) => ({ ...x, [l.id]: v }))}
                                aria-label={`${t(T.titre)} : ${l.nom}`}
                                className="cursor-pointer"
                            />
                        </label>
                    ))}
                </div>
            )}
        </section>
    );
}
