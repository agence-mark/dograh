"use client";

/**
 * [.mark] U6 (J3) : « Juge des vrais appels », un réglage PAR AGENT, dans le thème Qualité.
 *
 * Lu et écrit côté serveur (`GET|PUT /workflow/{id}/juge-vrais-appels`) ; éteint par défaut. Allumé, l'après-appel juge les vrais
 * appels de l'agent avec le juge du Labo (Réglages du Labo › Juge), sans nœud à poser.
 *
 * RA-B (R6, audit 06) : trois filtres repris du « Contrôle qualité » de Dograh (part jugée de 1 à 100 %, durée minimale, répondeurs
 * exclus), et le libellé « allumé mais pas réglé » quand le juge du Labo est éteint ou sans clé (jusque-là l'après-appel ne faisait
 * rien, en silence). Les bornes sont celles du serveur (`routes/reglages_agent.py`). Une lecture ou un enregistrement qui échoue le
 * dit, sans inventer d'état.
 *
 * RA-C (06 point 6) : la dépense du mois du juge (jetons, dollars, budget) est dite sous l'interrupteur, lue sur la même route que celle de
 * l'appelant simulé (`/appel-simule/depense`, compteur unique de SA-3) ; illisible, la ligne disparaît au lieu d'afficher un faux zéro.
 */
import { useEffect, useState } from "react";

import {
    getDepenseDesRolesApiV1AppelSimuleDepenseGet,
    lireLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsGet,
    reglerLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsPut,
} from "@/client/sdk.gen";
import { Input } from "@/components/ui/input";

import { montant } from "../appelant-simule/montant";
import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { Info } from "../studio/marques";

const PART = { min: 1, max: 100 };
const DUREE = { min: 0, max: 600 };

interface DepenseDuJuge {
    jetons: number;
    cout: number;
    budget_mois: number;
    atteint: boolean;
}

interface Vue {
    actif: boolean;
    part: number;
    duree_min_s: number;
    repondeurs_exclus: boolean;
    etat_du_juge: string;
}

const TEXTES = {
    libelle: { en: "Judge the real calls", fr: "Juge des vrais appels" },
    info: {
        en: "After each real call of this agent, the judge set in the Labo settings rates it criterion by criterion, with a proof. Off by default. On Claude Code, the call waits in « To judge ».",
        fr: "Après chaque vrai appel de cet agent, le juge réglé dans les Réglages du Labo le note critère par critère, avec une preuve. Éteint par défaut. Sur Claude Code, l'appel attend dans « À juger ».",
    },
    part: { en: "Share of calls judged (%)", fr: "Part des appels jugés (%)" },
    duree: { en: "Minimum duration (seconds)", fr: "Durée minimale (secondes)" },
    repondeurs: { en: "Skip answering machines", fr: "Exclure les répondeurs" },
    aideFiltres: {
        en: "Filters that limit what the judge spends: a call that is not judged says why in its page.",
        fr: "Des filtres qui bornent la dépense du juge : un appel non jugé dit pourquoi sur sa page.",
    },
    depense: { en: "Spent this month", fr: "Dépensé ce mois-ci" },
    jetons: { en: "tokens", fr: "jetons" },
    surBudget: { en: "of", fr: "sur" },
    aucunPlafond: { en: "no cap", fr: "aucun plafond" },
    budgetAtteint: {
        en: "Budget reached: new calls are not judged. Raise it in the Labo settings › Simulated caller.",
        fr: "Budget atteint : les nouveaux appels ne sont pas jugés. Relevez-le dans les Réglages du Labo › Appelant simulé.",
    },
    illisible: { en: "Could not read or save this setting", fr: "Réglage illisible ou non enregistré" },
    enregistre: { en: "Judge setting saved.", fr: "Réglage du juge enregistré." },
    pasRegle: { en: "Switched on but not set up", fr: "Allumé mais pas réglé" },
    eteint: {
        en: "The Labo judge is switched off: no real call is judged. Switch it on in the Labo settings › Simulated caller.",
        fr: "Le juge du Labo est éteint : aucun vrai appel n'est jugé. Allumez-le dans les Réglages du Labo › Appelant simulé.",
    },
    sansCle: {
        en: "The Labo judge has no key: no real call is judged. Choose its key in the Labo settings › Simulated caller.",
        fr: "Le juge du Labo n'a pas de clé : aucun vrai appel n'est jugé. Choisissez sa clé dans les Réglages du Labo › Appelant simulé.",
    },
} satisfies Record<string, Texte>;

const horsBornes = (valeur: number, b: { min: number; max: number }) => !Number.isInteger(valeur) || valeur < b.min || valeur > b.max;

export function JugeDesVraisAppels({ workflowId }: { workflowId: number }) {
    const { t, langue } = useLangue();
    const [vue, setVue] = useState<Vue | null>(null);
    const [depense, setDepense] = useState<DepenseDuJuge | null>(null);
    const [erreur, setErreur] = useState(false);
    const [saisie, setSaisie] = useState<{ part: string; duree: string }>({ part: "100", duree: "0" });
    const [fautes, setFautes] = useState<{ part?: Texte; duree?: Texte }>({});

    const adopter = (v: Vue) => {
        setVue(v);
        setSaisie({ part: String(v.part), duree: String(v.duree_min_s) });
    };

    useEffect(() => {
        let annule = false;
        void lireLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsGet({ path: { workflow_id: workflowId } }).then((reponse) => {
            if (annule) return;
            const d = reponse?.data;
            if (reponse?.error || !d) setErreur(true);
            else
                adopter({
                    actif: Boolean(d.actif),
                    part: d.part ?? 100,
                    duree_min_s: d.duree_min_s ?? 0,
                    repondeurs_exclus: Boolean(d.repondeurs_exclus),
                    etat_du_juge: d.etat_du_juge ?? "regle",
                });
        });
        void getDepenseDesRolesApiV1AppelSimuleDepenseGet().then((reponse) => {
            const j = reponse?.error ? undefined : reponse?.data?.juge;
            if (!annule) setDepense(j ? { jetons: j.jetons ?? 0, cout: j.cout ?? 0, budget_mois: j.budget_mois ?? 0, atteint: Boolean(j.atteint) } : null);
        });
        return () => {
            annule = true;
        };
    }, [workflowId]);

    const enregistrer = async (corps: { actif: boolean; part?: number; duree_min_s?: number; repondeurs_exclus?: boolean }) => {
        setErreur(false);
        const reponse = await reglerLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsPut({
            path: { workflow_id: workflowId },
            body: corps,
        });
        const d = reponse?.data;
        if (reponse?.error || !d) {
            setErreur(true);
            notifier.echec(TEXTES.illisible);
            return;
        }
        adopter({
            actif: Boolean(d.actif),
            part: d.part ?? 100,
            duree_min_s: d.duree_min_s ?? 0,
            repondeurs_exclus: Boolean(d.repondeurs_exclus),
            etat_du_juge: d.etat_du_juge ?? "regle",
        });
        notifier.succes(TEXTES.enregistre);
    };

    const valider = (cle: "part" | "duree") => {
        const brut = saisie[cle].trim();
        const valeur = Number(brut);
        const bornes = cle === "part" ? PART : DUREE;
        if (brut === "" || horsBornes(valeur, bornes)) {
            setFautes((f) => ({
                ...f,
                [cle]: { en: `Enter a whole number between ${bornes.min} and ${bornes.max}.`, fr: `Saisissez un entier entre ${bornes.min} et ${bornes.max}.` },
            }));
            return;
        }
        setFautes((f) => ({ ...f, [cle]: undefined }));
        if (!vue || (cle === "part" ? vue.part : vue.duree_min_s) === valeur) return;
        void enregistrer(cle === "part" ? { actif: vue.actif, part: valeur } : { actif: vue.actif, duree_min_s: valeur });
    };

    const libelle = t(TEXTES.libelle);
    const pasRegle = vue?.actif === true && vue.etat_du_juge !== "regle";
    return (
        <div className="space-y-2 text-sm" data-testid="juge-vrais-appels">
            <div className="flex items-center gap-2">
                <input
                    type="checkbox"
                    className="size-4 cursor-pointer"
                    checked={vue?.actif === true}
                    disabled={vue === null}
                    onChange={(e) => void enregistrer({ actif: e.target.checked })}
                    aria-label={libelle}
                />
                <span>{libelle}</span>
                <Info>{t(TEXTES.info)}</Info>
                {erreur && (
                    <span data-erreur="juge-vrais-appels" className="text-destructive">
                        {t(TEXTES.illisible)}
                    </span>
                )}
            </div>
            {vue?.actif && depense && (
                <p className="text-xs text-muted-foreground" data-depense-du-juge>
                    <span className="font-medium text-foreground">{t(TEXTES.depense)}</span> {montant(depense.cout, langue)} $ ·{" "}
                    {depense.jetons.toLocaleString(langue === "fr" ? "fr-FR" : "en-US")} {t(TEXTES.jetons)} ·{" "}
                    {depense.budget_mois > 0 ? `${t(TEXTES.surBudget)} ${depense.budget_mois} $` : t(TEXTES.aucunPlafond)}
                    {depense.atteint && <span className="block text-destructive">{t(TEXTES.budgetAtteint)}</span>}
                </p>
            )}
            {pasRegle && (
                <p role="status" className="text-xs text-muted-foreground" data-etat-du-juge={vue.etat_du_juge}>
                    <span className="font-medium text-foreground">{t(TEXTES.pasRegle)}.</span>{" "}
                    {t(vue.etat_du_juge === "sans_cle" ? TEXTES.sansCle : TEXTES.eteint)}
                </p>
            )}
            {vue?.actif && (
                <div className="space-y-2 pl-6" data-filtres-du-juge>
                    <p className="text-xs text-muted-foreground">{t(TEXTES.aideFiltres)}</p>
                    <div className="grid max-w-md gap-2">
                        <label className="flex items-center justify-between gap-3" data-filtre="part">
                            <span>{t(TEXTES.part)}</span>
                            <Input
                                type="number"
                                className="w-24"
                                min={PART.min}
                                max={PART.max}
                                value={saisie.part}
                                aria-label={t(TEXTES.part)}
                                onChange={(e) => setSaisie((s) => ({ ...s, part: e.target.value }))}
                                onBlur={() => valider("part")}
                            />
                        </label>
                        {fautes.part && <p className="text-xs text-destructive">{t(fautes.part)}</p>}
                        <label className="flex items-center justify-between gap-3" data-filtre="duree">
                            <span>{t(TEXTES.duree)}</span>
                            <Input
                                type="number"
                                className="w-24"
                                min={DUREE.min}
                                max={DUREE.max}
                                value={saisie.duree}
                                aria-label={t(TEXTES.duree)}
                                onChange={(e) => setSaisie((s) => ({ ...s, duree: e.target.value }))}
                                onBlur={() => valider("duree")}
                            />
                        </label>
                        {fautes.duree && <p className="text-xs text-destructive">{t(fautes.duree)}</p>}
                        <label className="flex cursor-pointer items-center gap-2" data-filtre="repondeurs">
                            <input
                                type="checkbox"
                                className="size-4 cursor-pointer"
                                checked={vue.repondeurs_exclus}
                                aria-label={t(TEXTES.repondeurs)}
                                onChange={(e) => void enregistrer({ actif: vue.actif, repondeurs_exclus: e.target.checked })}
                            />
                            <span>{t(TEXTES.repondeurs)}</span>
                        </label>
                    </div>
                </div>
            )}
        </div>
    );
}
