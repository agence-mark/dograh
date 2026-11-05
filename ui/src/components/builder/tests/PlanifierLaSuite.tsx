"use client";

/**
 * [.mark] Partie 3, sous-lot 6 (SE-11 = D-3): « Planifier la suite ». Same shape as the mockup (`tests-plus.tsx`, `FenetrePlanifier`):
 * a switch, when, tries per test, who is told, the last scheduled runs. Two services behind it, one window:
 *  - the scheduled replay of the agent's suite (OFF by default: each try plays a simulated caller and a judge, which spends);
 *  - the alert « a version does worse than the previous one » (the first type of the agent alert service), with its thresholds,
 *    its e-mail, and « Check now ». An alert never rolls anything back: it says, and points to « To improve » (origin Deployment).
 * Nothing is saved until « Save » (a change not saved is asked about before leaving).
 */
import { CalendarClock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost,
    lireLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdGet,
    lireLesAlertesApiV1BuilderAlertesWorkflowIdGet,
    reglerLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdPut,
    reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut,
} from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp, Section, Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const TYPE = "version_moins_bien";

export interface Rejeu {
    actif: boolean;
    frequence: "quotidien" | "hebdomadaire";
    jour: number;
    heure: number;
    repetitions: number;
    derniere: Resultat | null;
    historique: Resultat[];
}
export interface Resultat {
    periode: string;
    statut: "joue" | "interrompu" | "echec" | "sans_tests";
    ok?: boolean;
    reussis?: number | null;
    total?: number | null;
    version?: number | null;
    erreur?: string;
}
export interface AlerteLevee {
    id: string;
    type: string;
    version: number;
    contre: number;
    resume: string;
    levee_le?: string;
    notifiee?: boolean;
}
export interface Alertes {
    mail: boolean;
    types: Record<string, { actif: boolean; seuils: Record<string, number> }>;
    levees: AlerteLevee[];
}

const JOURS = [
    { valeur: "0", fr: "Lundi", en: "Monday" },
    { valeur: "1", fr: "Mardi", en: "Tuesday" },
    { valeur: "2", fr: "Mercredi", en: "Wednesday" },
    { valeur: "3", fr: "Jeudi", en: "Thursday" },
    { valeur: "4", fr: "Vendredi", en: "Friday" },
    { valeur: "5", fr: "Samedi", en: "Saturday" },
    { valeur: "6", fr: "Dimanche", en: "Sunday" },
];

const nombre = (v: string, defaut: number) => {
    const n = Number(v.replace(",", "."));
    return Number.isFinite(n) ? n : defaut;
};

export function PlanifierLaSuite({ agentId, fermer, onChange }: { agentId: number; fermer: () => void; onChange?: () => void }) {
    const { t } = useLangue();
    const [rejeu, setRejeu] = useState<Rejeu | null>(null);
    const [alertes, setAlertes] = useState<Alertes | null>(null);
    const [depart, setDepart] = useState("");
    const [erreur, setErreur] = useState(false);
    const [envoi, setEnvoi] = useState(false);
    const [verification, setVerification] = useState(false);

    const charger = useCallback(async () => {
        const [a, b] = await Promise.all([
            lireLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdGet({ path: { workflow_id: agentId } }),
            lireLesAlertesApiV1BuilderAlertesWorkflowIdGet({ path: { workflow_id: agentId } }),
        ]);
        if (a.error || b.error) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setRejeu(a.data as unknown as Rejeu);
        setAlertes(b.data as unknown as Alertes);
        setDepart(JSON.stringify([a.data, b.data]));
    }, [agentId]);
    useEffect(() => {
        void charger();
    }, [charger]);

    const modifie = rejeu !== null && alertes !== null && JSON.stringify([rejeu, alertes]) !== depart;
    const regle = alertes?.types[TYPE];

    const enregistrer = async () => {
        if (!rejeu || !alertes || !regle) return;
        setEnvoi(true);
        const [a, b] = await Promise.all([
            reglerLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdPut({
                path: { workflow_id: agentId },
                body: { actif: rejeu.actif, frequence: rejeu.frequence, jour: rejeu.jour, heure: rejeu.heure, repetitions: rejeu.repetitions },
            }),
            reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut({
                path: { workflow_id: agentId },
                body: { mail: alertes.mail, types: { [TYPE]: { actif: regle.actif, seuils: regle.seuils } } },
            }),
        ]);
        setEnvoi(false);
        if (a.error || b.error) {
            notifier.echec(
                { fr: "Enregistrement impossible. Vérifiez les valeurs et réessayez.", en: "Could not save. Check the values and try again." },
                { erreur: a.error ?? b.error, reessayer: () => void enregistrer() },
            );
            return;
        }
        setRejeu(a.data as unknown as Rejeu);
        setAlertes(b.data as unknown as Alertes);
        setDepart(JSON.stringify([a.data, b.data]));
        notifier.succes({ fr: "Planification et alerte enregistrées.", en: "Schedule and alert saved." });
        onChange?.();
    };

    const verifier = async () => {
        setVerification(true);
        const r = await evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost({ path: { workflow_id: agentId } });
        setVerification(false);
        if (r.error) {
            notifier.echec({ fr: "Vérification impossible. Réessayez.", en: "Could not check. Try again." }, { erreur: r.error, reessayer: () => void verifier() });
            return;
        }
        const donnees = r.data as unknown as { alertes: Array<{ statut: string }> };
        await charger();
        if (donnees.alertes.some((a) => a.statut === "levee")) {
            notifier.avertissement({ fr: "Une version fait moins bien. Voyez « À améliorer ».", en: "A version does worse. See « To improve »." });
            onChange?.();
        } else {
            notifier.information({ fr: "Aucune version ne fait moins bien que la précédente.", en: "No version does worse than the previous one." });
        }
    };

    const majSeuil = (nom: string, valeur: number) => regle && alertes && setAlertes({ ...alertes, types: { ...alertes.types, [TYPE]: { ...regle, seuils: { ...regle.seuils, [nom]: valeur } } } });

    return (
        <FenetreOnglets
            fermer={fermer}
            modifie={modifie}
            titre={
                <>
                    <CalendarClock className="size-5" /> {t({ en: "Schedule the suite", fr: "Planifier la suite" })}
                </>
            }
            sous={t({
                en: "Replays the agent's suite at a fixed time, to see an agent get worse when nobody changed anything. Nothing is ever rolled back by itself.",
                fr: "Rejoue la suite de l'agent à date fixe, pour voir un agent se dégrader alors que personne n'a rien changé. Rien n'est jamais retiré tout seul.",
            })}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            onValider={() => void enregistrer()}
            desactiver={!modifie || envoi}
        >
            {erreur ? (
                <EtatVide cas="erreur" reessayer={() => void charger()} />
            ) : !rejeu || !alertes || !regle ? (
                <EtatVide cas="chargement" lignes={5} />
            ) : (
                <>
                    <Section titre={t({ en: "Scheduled replay", fr: "Rejeu planifié" })}>
                        <Champs>
                            <LigneChamp
                                libelle={t({ en: "Schedule on", fr: "Planification allumée" })}
                                info={t({
                                    en: "Off by default: every try plays a simulated caller and a judge, which spends. Turning it off stops it, even a replay under way.",
                                    fr: "Éteinte par défaut : chaque essai joue un appelant simulé et un juge, ce qui dépense. L'éteindre l'arrête, même un rejeu en cours.",
                                })}
                            >
                                <Switch checked={rejeu.actif} onCheckedChange={(v) => setRejeu({ ...rejeu, actif: v })} aria-label={t({ en: "Schedule on", fr: "Planification allumée" })} />
                            </LigneChamp>
                            {rejeu.actif && (
                                <>
                                    <LigneChamp libelle={t({ en: "When", fr: "Quand" })}>
                                        <span className="flex items-center gap-2">
                                            <Segmente
                                                valeur={rejeu.frequence === "quotidien" ? t({ en: "Every day", fr: "Chaque jour" }) : t({ en: "Every week", fr: "Chaque semaine" })}
                                                options={[t({ en: "Every day", fr: "Chaque jour" }), t({ en: "Every week", fr: "Chaque semaine" })]}
                                                changer={(v) => setRejeu({ ...rejeu, frequence: v === t({ en: "Every day", fr: "Chaque jour" }) ? "quotidien" : "hebdomadaire" })}
                                            />
                                            {rejeu.frequence === "hebdomadaire" && (
                                                <Liste
                                                    className="w-32"
                                                    valeur={String(rejeu.jour)}
                                                    changer={(v) => setRejeu({ ...rejeu, jour: Number(v) })}
                                                    options={JOURS.map((j) => ({ valeur: j.valeur, libelle: t(j) }))}
                                                />
                                            )}
                                            <Input
                                                type="number"
                                                min={0}
                                                max={23}
                                                value={rejeu.heure}
                                                aria-label={t({ en: "Hour (Paris time)", fr: "Heure (heure de Paris)" })}
                                                onChange={(e) => setRejeu({ ...rejeu, heure: Math.max(0, Math.min(23, Math.trunc(nombre(e.target.value, 3)))) })}
                                                className="h-8 w-20"
                                            />
                                            <span className="text-sm text-muted-foreground">h</span>
                                        </span>
                                    </LigneChamp>
                                    <LigneChamp
                                        libelle={t({ en: "Tries per test", fr: "Essais par test" })}
                                        info={t({ en: "More tries, fewer false alarms; each try costs a simulated call. 3 at most.", fr: "Plus d'essais, moins de fausses alertes ; chaque essai coûte un appel simulé. 3 au plus." })}
                                    >
                                        <Liste className="w-24" valeur={String(rejeu.repetitions)} changer={(v) => setRejeu({ ...rejeu, repetitions: Number(v) })} options={["1", "2", "3"]} />
                                    </LigneChamp>
                                    <LigneChamp
                                        libelle={t({ en: "What is replayed", fr: "Ce qui est rejoué" })}
                                        info={t({
                                            en: "The whole suite of the agent, on its draft, with its tools simulated. A test that fails goes to « To improve ».",
                                            fr: "Toute la suite de l'agent, sur son brouillon, ses outils simulés. Un test qui échoue entre dans « À améliorer ».",
                                        })}
                                    >
                                        <span className="text-sm">{t({ en: "The whole suite", fr: "Toute la suite" })}</span>
                                    </LigneChamp>
                                </>
                            )}
                        </Champs>
                    </Section>
                    <Section
                        titre={t({ en: "Alert: a version does worse", fr: "Alerte : une version fait moins bien" })}
                        info={t({
                            en: "Compares the latest live version with the one before it, on real calls (judge's score out of 5, share of calls with a dead end). It says and points to « To improve » with the origin Deployment. It never removes or changes a version.",
                            fr: "Compare la dernière version en ligne à celle d'avant, sur les vrais appels (note du juge sur 5, part d'appels avec impasse). Elle dit et pointe vers « À améliorer » avec l'origine Déploiement. Elle ne retire ni ne change jamais une version.",
                        })}
                    >
                        <Champs>
                            <LigneChamp libelle={t({ en: "Alert on", fr: "Alerte allumée" })}>
                                <Switch
                                    checked={regle.actif}
                                    onCheckedChange={(v) => setAlertes({ ...alertes, types: { ...alertes.types, [TYPE]: { ...regle, actif: v } } })}
                                    aria-label={t({ en: "Alert on", fr: "Alerte allumée" })}
                                />
                            </LigneChamp>
                            {regle.actif && (
                                <>
                                    <LigneChamp libelle={t({ en: "Score drop from", fr: "Baisse de la note à partir de" })} info={t({ en: "In points out of 5.", fr: "En points sur 5." })}>
                                        <Input type="number" step="0.1" min={0.1} max={4} value={regle.seuils.baisse_note} aria-label={t({ en: "Score drop", fr: "Baisse de la note" })} onChange={(e) => majSeuil("baisse_note", nombre(e.target.value, regle.seuils.baisse_note))} className="h-8 w-24" />
                                    </LigneChamp>
                                    <LigneChamp libelle={t({ en: "Dead ends up by", fr: "Hausse des impasses de" })} info={t({ en: "In points of percentage: 5 means 5 % more calls with a dead end.", fr: "En points de pourcentage : 5 veut dire 5 % d'appels avec impasse en plus." })}>
                                        <Input
                                            type="number"
                                            step="1"
                                            min={1}
                                            max={100}
                                            value={Math.round(regle.seuils.hausse_impasses * 100)}
                                            aria-label={t({ en: "Dead ends up by", fr: "Hausse des impasses" })}
                                            onChange={(e) => majSeuil("hausse_impasses", nombre(e.target.value, regle.seuils.hausse_impasses * 100) / 100)}
                                            className="h-8 w-24"
                                        />
                                    </LigneChamp>
                                    <LigneChamp libelle={t({ en: "Calls needed per version", fr: "Appels nécessaires par version" })} info={t({ en: "Below this, nothing is said: noise is not a regression.", fr: "En dessous, rien n'est dit : du bruit n'est pas une régression." })}>
                                        <Input type="number" min={3} max={1000} value={regle.seuils.appels_min} aria-label={t({ en: "Calls needed", fr: "Appels nécessaires" })} onChange={(e) => majSeuil("appels_min", Math.trunc(nombre(e.target.value, regle.seuils.appels_min)))} className="h-8 w-24" />
                                    </LigneChamp>
                                    <LigneChamp
                                        libelle={t({ en: "Tell by e-mail", fr: "Prévenir par e-mail" })}
                                        info={t({ en: "Off by default. Goes once per alert to the notification addresses of the organization and of .mark.", fr: "Éteint par défaut. Part une fois par alerte vers les adresses de notification de l'organisation et de .mark." })}
                                    >
                                        <Switch checked={alertes.mail} onCheckedChange={(v) => setAlertes({ ...alertes, mail: v })} aria-label={t({ en: "Tell by e-mail", fr: "Prévenir par e-mail" })} />
                                    </LigneChamp>
                                </>
                            )}
                        </Champs>
                        <div className="pt-3">
                            <Button variant="outline" size="sm" disabled={verification || modifie} onClick={() => void verifier()}>
                                {verification ? t({ en: "Checking…", fr: "Vérification…" }) : t({ en: "Check now", fr: "Vérifier maintenant" })}
                            </Button>
                            {modifie && <span className="ml-2 text-xs text-muted-foreground">{t({ en: "Save first.", fr: "Enregistrez d'abord." })}</span>}
                        </div>
                        {alertes.levees.length > 0 && (
                            <ul className="divide-y border-t pt-1 text-sm" data-testid="alertes-levees">
                                {alertes.levees.map((a) => (
                                    <li key={a.id} className="py-2">
                                        <span className="font-medium">{a.resume}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </Section>
                    <Section titre={t({ en: "Last scheduled runs", fr: "Dernières exécutions planifiées" })}>
                        {rejeu.historique.length === 0 ? (
                            <p className="text-sm text-muted-foreground">{t({ en: "Nothing played yet.", fr: "Rien n'a encore été joué." })}</p>
                        ) : (
                            <table className="w-full text-sm" data-testid="historique-planifie">
                                <tbody className="divide-y border-t">
                                    {rejeu.historique.map((h) => (
                                        <tr key={h.periode}>
                                            <td className="py-2.5">{h.periode}</td>
                                            <td className="pl-4 text-muted-foreground">{h.version ? `v${h.version}` : ""}</td>
                                            <td className="pl-4 text-right">
                                                {h.statut === "joue" ? (
                                                    <span className={h.ok ? "" : "text-destructive"}>
                                                        {h.reussis ?? "?"}/{h.total ?? "?"}
                                                        {h.ok ? "" : ` · ${t({ en: "regression", fr: "régression" })}`}
                                                    </span>
                                                ) : h.statut === "sans_tests" ? (
                                                    t({ en: "no test", fr: "aucun test" })
                                                ) : h.statut === "interrompu" ? (
                                                    t({ en: "stopped (too long)", fr: "arrêté (trop long)" })
                                                ) : (
                                                    t({ en: "could not run", fr: "non jouable" })
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                        <p className="flex items-center gap-1.5 pt-3 text-xs text-muted-foreground">
                            {t({ en: "A test that used to pass and now fails goes to « To improve ».", fr: "Un test qui réussissait et qui échoue entre dans « À améliorer »." })}
                            <Info>{t({ en: "With its version and its date, as for a replay by hand.", fr: "Avec sa version et sa date, comme pour un rejeu à la main." })}</Info>
                        </p>
                    </Section>
                </>
            )}
        </FenetreOnglets>
    );
}
