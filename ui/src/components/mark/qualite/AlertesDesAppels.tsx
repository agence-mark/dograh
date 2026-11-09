"use client";

/**
 * [.mark] Partie 3, L3e sous-lot 1: the alerts on REAL calls (audit 12 § 3, mockup « Alertes »). Five signals of the one agent alert
 * service (judge fails, transfers, safeguards triggered, outages, latency), each compared with the period of the same length before.
 * « Triggered » lists what rose, with « See the calls » (the calls that count, each opens its page). « Thresholds » is one row per
 * signal; a click opens its window. Nothing here spends (no model is called) and nothing rolls back or changes an agent.
 * The settings are the agent's: the page picks the agent first.
 */
import { BellRing, Mail } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost,
    lireLaQualiteApiV1QualiteGet,
    lireLesAlertesApiV1BuilderAlertesWorkflowIdGet,
    reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut,
} from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

/** The five signals of real calls (the sixth type of the service, « a version does worse », has its own window on the Tests tab). */
export const SIGNAUX_DES_APPELS = ["hausse_rates", "hausse_transferts", "hausse_garde_fous", "hausse_pannes", "hausse_latence"] as const;

type Seuils = Record<string, number>;
type Reglage = { actif: boolean; seuils: Seuils };
type Levee = {
    id: string;
    type: string;
    resume: string;
    levee_le?: string;
    appels?: number[];
    appels_concernes?: number;
    periode_jours?: number;
    notifiee?: boolean;
};
type Vue = {
    mail: boolean;
    types: Record<string, Reglage>;
    levees: Levee[];
    /** Clôture D2 (É63) : où en est chaque signal à cet instant (hausse en %, `null` : pas mesurable), et les appels lus. */
    maintenant?: Record<string, { hausse: number | null; appels: number }>;
    catalogue: Record<string, { titre: { fr: string; en: string }; explication: { fr: string; en: string }; seuils: Record<string, { defaut: number; bas: number; haut: number }> }>;
};

const nombre = (v: string, defaut: number) => {
    const n = Number(v.replace(",", "."));
    return Number.isFinite(n) ? n : defaut;
};

/** « Maintenant » : la hausse du signal contre la période d'avant ; un tiret quand elle n'est pas mesurable (jamais un zéro inventé). */
export const maintenantDit = (hausse: number | null | undefined): string =>
    hausse === null || hausse === undefined ? "–" : `${hausse > 0 ? "+" : ""}${String(hausse).replace(".", ",")} %`;

export function AlertesDesAppels() {
    const { t } = useLangue();
    const [agents, setAgents] = useState<{ id: number; nom: string }[] | null>(null);
    const [agent, setAgent] = useState<number | null>(null);
    const [vue, setVue] = useState<Vue | null>(null);
    const [erreur, setErreur] = useState(false);
    const [edition, setEdition] = useState<string | null>(null);
    const [ouverte, setOuverte] = useState<string | null>(null);
    const [verification, setVerification] = useState(false);

    useEffect(() => {
        let vivant = true;
        void lireLaQualiteApiV1QualiteGet({ query: { jours: 30 } }).then((r) => {
            if (!vivant) return;
            if (r.error || !r.data) {
                setErreur(true);
                return;
            }
            const liste = ((r.data as unknown as { agents: { workflow_id: number; workflow_nom: string }[] }).agents ?? []).map((a) => ({ id: a.workflow_id, nom: a.workflow_nom }));
            setAgents(liste);
            setAgent((courant) => courant ?? liste[0]?.id ?? null);
        });
        return () => {
            vivant = false;
        };
    }, []);

    const charger = useCallback(async (id: number) => {
        const r = await lireLesAlertesApiV1BuilderAlertesWorkflowIdGet({ path: { workflow_id: id } });
        if (r.error || !r.data) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setVue(r.data as unknown as Vue);
    }, []);
    useEffect(() => {
        if (agent !== null) void charger(agent);
    }, [agent, charger]);

    const declenchees = (vue?.levees ?? []).filter((a) => (SIGNAUX_DES_APPELS as readonly string[]).includes(a.type));

    const verifier = async () => {
        if (agent === null) return;
        setVerification(true);
        const r = await evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost({ path: { workflow_id: agent } });
        setVerification(false);
        if (r.error) {
            notifier.echec({ fr: "Vérification impossible. Réessayez.", en: "Could not check. Try again." }, { erreur: r.error, reessayer: () => void verifier() });
            return;
        }
        await charger(agent);
        notifier.information({ fr: "Les seuils ont été revérifiés.", en: "The thresholds were checked again." });
    };

    if (erreur) return <EtatVide cas="erreur" reessayer={() => window.location.reload()} />;
    if (agents === null) return <EtatVide cas="chargement" lignes={4} />;
    if (agent === null)
        return <EtatVide cas="premier" icone={BellRing} titre={t({ fr: "Aucun agent n'a encore reçu d'appel : les seuils se règlent par agent", en: "No agent has received a call yet: thresholds are set per agent" })} />;

    return (
        <div className="space-y-6" data-testid="alertes-des-appels">
            <div className="flex flex-wrap items-center gap-3">
                <Liste
                    className="w-64"
                    valeur={String(agent)}
                    changer={(v) => {
                        setVue(null);
                        setAgent(Number(v));
                    }}
                    options={agents.map((a) => ({ valeur: String(a.id), libelle: a.nom }))}
                />
                <Button variant="outline" size="sm" disabled={verification} onClick={() => void verifier()}>
                    {verification ? t({ en: "Checking…", fr: "Vérification…" }) : t({ en: "Check now", fr: "Vérifier maintenant" })}
                </Button>
            </div>
            {!vue ? (
                <EtatVide cas="chargement" lignes={4} />
            ) : (
                <>
                    <section>
                        <TitreTableau titre={t({ en: "Triggered", fr: "Déclenchées" })} />
                        {declenchees.length === 0 ? (
                            <EtatVide cas="fait" titre={t({ en: "No alert triggered", fr: "Aucune alerte déclenchée" })} donnee={t({ en: "The thresholds are checked after each call", fr: "Les seuils sont surveillés après chaque appel" })} />
                        ) : (
                            <ul className="divide-y" data-testid="alertes-declenchees">
                                {declenchees.map((a) => (
                                    <li key={a.id} className="py-3 text-sm">
                                        <div className="flex items-center gap-3">
                                            <span className="size-2 shrink-0 rounded-full bg-(--signal-danger)" aria-label={t({ en: "Triggered", fr: "Déclenchée" })} />
                                            <span className="flex-1">
                                                <span className="font-medium">{t(vue.catalogue[a.type]?.titre ?? { fr: a.type, en: a.type })}</span>
                                                <span className="block text-xs text-muted-foreground">{a.resume}</span>
                                            </span>
                                            <Button size="sm" className="h-7" onClick={() => setOuverte(ouverte === a.id ? null : a.id)} aria-expanded={ouverte === a.id}>
                                                {t({ en: "See the calls", fr: "Voir les appels" })}
                                            </Button>
                                        </div>
                                        {ouverte === a.id && (
                                            <ul className="mt-2 flex flex-wrap gap-2 pl-5" data-testid="appels-concernes">
                                                {(a.appels ?? []).map((id) => (
                                                    <li key={id}>
                                                        <Link href={`/workflow/${agent}/run/${id}`} className="rounded-md border px-2 py-0.5 text-xs hover:font-medium">
                                                            {t({ en: `Call ${id}`, fr: `Appel ${id}` })}
                                                        </Link>
                                                    </li>
                                                ))}
                                                {(a.appels_concernes ?? 0) > (a.appels?.length ?? 0) && (
                                                    <li className="text-xs text-muted-foreground">
                                                        {t({ en: `${(a.appels_concernes ?? 0) - (a.appels?.length ?? 0)} more`, fr: `${(a.appels_concernes ?? 0) - (a.appels?.length ?? 0)} de plus` })}
                                                    </li>
                                                )}
                                            </ul>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>
                    <section>
                        <TitreTableau
                            titre={t({ en: "Thresholds", fr: "Seuils" })}
                            info={<Info>{t({ en: "An alert goes off when a signal rises by at least the threshold against the period of the same length before, over at least the number of calls asked. Nothing here calls a model or spends.", fr: "Une alerte part quand le signal monte d'au moins le seuil par rapport à la période de même durée qui précède, sur au moins le nombre d'appels demandé. Rien ici n'appelle de modèle ni ne dépense." })}</Info>}
                        />
                        <Tableau colonnes={[{ titre: t({ en: "Signal", fr: "Signal" }) }, { titre: t({ en: "Threshold", fr: "Seuil" }), droite: true }, { titre: t({ en: "Now", fr: "Maintenant" }), droite: true }, { titre: t({ en: "Period", fr: "Période" }) }, { titre: t({ en: "Tell", fr: "Prévenir" }) }, { titre: t({ en: "State", fr: "État" }) }]}>
                            {SIGNAUX_DES_APPELS.map((code) => {
                                const r = vue.types[code];
                                const en_cours = declenchees.some((a) => a.type === code);
                                return (
                                    <Ligne key={code} onClick={() => setEdition(code)}>
                                        <Cellule principale>{t(vue.catalogue[code].titre)}</Cellule>
                                        <Cellule droite>+{r.seuils.hausse} %</Cellule>
                                        <Cellule droite>
                                            <span data-maintenant={code}>{maintenantDit(vue.maintenant?.[code]?.hausse)}</span>
                                        </Cellule>
                                        <Cellule>{r.seuils.jours === 1 ? "24 h" : `${r.seuils.jours} j`}</Cellule>
                                        <Cellule>
                                            <span className="inline-flex items-center gap-2">
                                                <BellRing className="size-3.5" aria-label={t({ en: "Notification", fr: "Notification" })} />
                                                {vue.mail && <Mail className="size-3.5" aria-label={t({ en: "E-mail", fr: "E-mail" })} />}
                                            </span>
                                        </Cellule>
                                        <Cellule>
                                            {!r.actif ? (
                                                <PointEtat etat="brouillon">{t({ en: "Off", fr: "Éteinte" })}</PointEtat>
                                            ) : en_cours ? (
                                                <PointEtat etat="panne">{t({ en: "Triggered", fr: "Déclenchée" })}</PointEtat>
                                            ) : (
                                                <PointEtat etat="publie">{t({ en: "Watched", fr: "Surveillée" })}</PointEtat>
                                            )}
                                        </Cellule>
                                    </Ligne>
                                );
                            })}
                        </Tableau>
                    </section>
                    {edition && (
                        <FenetreSeuil
                            key={edition}
                            code={edition}
                            vue={vue}
                            agentId={agent}
                            fermer={() => setEdition(null)}
                            enregistre={(v) => {
                                setVue(v);
                                setEdition(null);
                            }}
                        />
                    )}
                </>
            )}
        </div>
    );
}

function FenetreSeuil({ code, vue, agentId, fermer, enregistre }: { code: string; vue: Vue; agentId: number; fermer: () => void; enregistre: (v: Vue) => void }) {
    const { t } = useLangue();
    const depart = vue.types[code];
    const bornes = vue.catalogue[code].seuils;
    const [regle, setRegle] = useState<Reglage>(depart);
    const [mail, setMail] = useState(vue.mail);
    const [envoi, setEnvoi] = useState(false);
    const modifie = JSON.stringify([regle, mail]) !== JSON.stringify([depart, vue.mail]);
    const hors = (nom: string) => !(regle.seuils[nom] >= bornes[nom].bas && regle.seuils[nom] <= bornes[nom].haut);
    const invalide = Object.keys(bornes).some(hors);
    const maj = (nom: string, valeur: number) => setRegle({ ...regle, seuils: { ...regle.seuils, [nom]: valeur } });

    const enregistrer = async () => {
        setEnvoi(true);
        const r = await reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut({ path: { workflow_id: agentId }, body: { mail, types: { [code]: { actif: regle.actif, seuils: regle.seuils } } } });
        setEnvoi(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Enregistrement impossible. Vérifiez les valeurs et réessayez.", en: "Could not save. Check the values and try again." }, { erreur: r.error, reessayer: () => void enregistrer() });
            return;
        }
        notifier.succes({ fr: "Seuil enregistré.", en: "Threshold saved." });
        enregistre(r.data as unknown as Vue);
    };

    const champ = (nom: string, libelle: { fr: string; en: string }, info: { fr: string; en: string }, entier = false) => (
        <LigneChamp libelle={t(libelle)} info={t(info)}>
            <span className="flex flex-col gap-1">
                <Input
                    type="number"
                    step={entier ? 1 : 5}
                    min={bornes[nom].bas}
                    max={bornes[nom].haut}
                    value={regle.seuils[nom]}
                    aria-label={t(libelle)}
                    aria-invalid={hors(nom)}
                    onChange={(e) => maj(nom, entier ? Math.trunc(nombre(e.target.value, regle.seuils[nom])) : nombre(e.target.value, regle.seuils[nom]))}
                    className="h-8 w-28"
                />
                {hors(nom) && (
                    <span className="text-xs text-destructive">
                        {t({ en: `Between ${bornes[nom].bas} and ${bornes[nom].haut}.`, fr: `Entre ${bornes[nom].bas} et ${bornes[nom].haut}.` })}
                    </span>
                )}
            </span>
        </LigneChamp>
    );

    return (
        <FenetreOnglets
            fermer={fermer}
            modifie={modifie}
            titre={t(vue.catalogue[code].titre)}
            sous={t(vue.catalogue[code].explication)}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            onValider={() => void enregistrer()}
            desactiver={!modifie || invalide || envoi}
        >
            <Champs>
                <LigneChamp libelle={t({ en: "Watch this signal", fr: "Surveiller ce signal" })}>
                    <Switch checked={regle.actif} onCheckedChange={(v) => setRegle({ ...regle, actif: v })} aria-label={t({ en: "Watch this signal", fr: "Surveiller ce signal" })} />
                </LigneChamp>
                {champ("hausse", { en: "Rise threshold (%)", fr: "Seuil de hausse (%)" }, { en: "The alert goes off when the signal rises by at least this share against the previous period.", fr: "L'alerte part quand le signal monte d'au moins cette part par rapport à la période précédente." })}
                {champ("jours", { en: "Period (days)", fr: "Période (jours)" }, { en: "1 for 24 h, 7 for a week, 30 for a month. Compared with the period of the same length just before.", fr: "1 pour 24 h, 7 pour une semaine, 30 pour un mois. Comparée à la période de même durée juste avant." }, true)}
                {champ("appels_min", { en: "Calls at least", fr: "Appels au minimum" }, { en: "Below this, no alert: too few calls to conclude.", fr: "En dessous, l'alerte ne part pas : trop peu d'appels pour conclure." }, true)}
                {champ("cas_min", { en: "Calls concerned at least", fr: "Appels concernés au minimum" }, { en: "Below this, a rise is only noise.", fr: "En dessous, une hausse n'est que du bruit." }, true)}
                <LigneChamp
                    libelle={t({ en: "Tell by e-mail", fr: "Prévenir par e-mail" })}
                    info={t({ en: "Off by default. One e-mail per alert, to the notification addresses of the organization and of .mark. It applies to all the agent's alerts.", fr: "Éteint par défaut. Un e-mail par alerte, vers les adresses de notification de l'organisation et de .mark. Vaut pour toutes les alertes de l'agent." })}
                >
                    <Switch checked={mail} onCheckedChange={setMail} aria-label={t({ en: "Tell by e-mail", fr: "Prévenir par e-mail" })} />
                </LigneChamp>
            </Champs>
        </FenetreOnglets>
    );
}
