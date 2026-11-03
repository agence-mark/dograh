"use client";

/**
 * [.mark] U11 (§ 17) : « Attaquer l'agent ». Conçu sans maquette (voir `14-ecarts-maquette.md`), avec les composants de la maquette.
 * Le contrat de périmètre est confirmé AVANT toute sonde (profondeur, agent attaqué tel qu'il est, rapport seul). Le rapport
 * sépare ce qui a tenu, ce qui a cédé, ce qui est plausible (cédé une fois, non reproduit), ce qui n'est pas testé (jamais
 * compté comme tenu) et ce qui n'est pas couvert.
 */
import { Play, RotateCcw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    dernierRapportApiV1BuilderAttaquesWorkflowIdGet,
    lancerLesAttaquesApiV1BuilderAttaquesWorkflowIdLancerPost,
    rejouerLesAttaquesApiV1BuilderAttaquesWorkflowIdRejouerPost,
} from "@/client/sdk.gen";
import type { RapportDAttaque } from "@/components/mark/agent/publication/types";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp, Section, Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info, Marque, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

const PROFONDEURS = ["rapide", "standard", "poussee"] as const;

export function FenetreAttaques({ agentId, fermer }: { agentId: number; fermer: () => void }) {
    const { t } = useLangue();
    const [rapport, setRapport] = useState<RapportDAttaque | null | undefined>(undefined);
    const [profondeur, setProfondeur] = useState<(typeof PROFONDEURS)[number]>("rapide");
    const [confirme, setConfirme] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState(false);

    const NOM = {
        rapide: t({ en: "Quick (about 15)", fr: "Rapide (environ 15)" }),
        standard: t({ en: "Standard (35 to 45)", fr: "Standard (35 à 45)" }),
        poussee: t({ en: "Deep (80 and more)", fr: "Poussée (80 et plus)" }),
    };
    const GRAVITE = {
        critique: t({ en: "critical", fr: "critique" }),
        haute: t({ en: "high", fr: "haute" }),
        moyenne: t({ en: "medium", fr: "moyenne" }),
        basse: t({ en: "low", fr: "basse" }),
    };

    const charger = useCallback(async () => {
        const r = await dernierRapportApiV1BuilderAttaquesWorkflowIdGet({ path: { workflow_id: agentId } });
        if (r.error) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setRapport(((r.data as { rapport?: RapportDAttaque | null } | undefined)?.rapport ?? null) as RapportDAttaque | null);
    }, [agentId]);
    useEffect(() => {
        void charger();
    }, [charger]);

    const lancer = async () => {
        if (!confirme || enCours) return;
        setEnCours(true);
        const r = await lancerLesAttaquesApiV1BuilderAttaquesWorkflowIdLancerPost({
            path: { workflow_id: agentId },
            body: { profondeur, confirme: true, modifie_l_environnement: false, corrige: false },
        });
        setEnCours(false);
        if (r.error) {
            notifier.echec({ fr: "Attaque impossible. Réessayez.", en: "Could not run the attack. Try again." }, { erreur: r.error, reessayer: () => void lancer() });
            return;
        }
        setRapport((r.data as { rapport: RapportDAttaque }).rapport);
        notifier.succes({ fr: "Attaque terminée. Le rapport est à jour.", en: "Attack finished. The report is up to date." });
    };

    const rejouer = async () => {
        if (enCours) return;
        setEnCours(true);
        const r = await rejouerLesAttaquesApiV1BuilderAttaquesWorkflowIdRejouerPost({ path: { workflow_id: agentId } });
        setEnCours(false);
        if (r.error) {
            notifier.echec({ fr: "Rejeu impossible. Réessayez.", en: "Could not replay. Try again." }, { erreur: r.error, reessayer: () => void rejouer() });
            return;
        }
        notifier.succes({ fr: "Échecs et échantillon rejoués.", en: "Failures and a sample replayed." });
        await charger();
    };

    const resume = rapport?.resume;
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={
                <>
                    <ShieldAlert className="size-5" /> {t({ en: "Attack the agent", fr: "Attaquer l'agent" })}
                </>
            }
            sous={t({
                en: "The agent is attacked as it is, in text, with its tools simulated. Nothing is changed: the report alone.",
                fr: "L'agent est attaqué tel qu'il est, en texte, ses outils simulés. Rien n'est modifié : le rapport seul.",
            })}
            valider={null}
            pied={
                <>
                    {rapport && (
                        <Button variant="outline" disabled={enCours} onClick={() => void rejouer()}>
                            <RotateCcw className="size-4" /> {t({ en: "Replay the failures", fr: "Rejouer les échecs" })}
                        </Button>
                    )}
                </>
            }
        >
            {erreur ? (
                <EtatVide cas="erreur" reessayer={() => void charger()} />
            ) : rapport === undefined ? (
                <EtatVide cas="chargement" lignes={4} />
            ) : (
                <>
                    <Section
                        titre={t({ en: "Scope", fr: "Périmètre" })}
                        info={t({
                            en: "Confirmed before any probe, and never widened during the run. The depth sets the number of probes; only the deep one repeats a probe to measure instability.",
                            fr: "Confirmé avant toute sonde, jamais élargi en cours de route. La profondeur fixe le nombre de sondes ; seule la poussée répète une sonde pour mesurer l'instabilité.",
                        })}
                    >
                        <Champs>
                            <LigneChamp libelle={t({ en: "Depth", fr: "Profondeur" })}>
                                <Segmente valeur={NOM[profondeur]} options={PROFONDEURS.map((p) => NOM[p])} changer={(v) => setProfondeur(PROFONDEURS.find((p) => NOM[p] === v) ?? "rapide")} />
                            </LigneChamp>
                            <div className="flex items-center gap-3 py-3 text-sm">
                                <Checkbox id="confirme-attaque" checked={confirme} onCheckedChange={(c) => setConfirme(c === true)} />
                                <label htmlFor="confirme-attaque" className="flex-1 cursor-pointer">
                                    {t({
                                        en: "I confirm this scope: the agent is attacked as it is, its environment is not changed, the report alone.",
                                        fr: "Je confirme ce périmètre : l'agent est attaqué tel qu'il est, son environnement n'est pas modifié, rapport seul.",
                                    })}
                                </label>
                                <Button disabled={!confirme || enCours} onClick={() => void lancer()}>
                                    <Play className="size-4" />
                                    {enCours ? t({ en: "Attacking…", fr: "Attaque en cours…" }) : t({ en: "Attack", fr: "Attaquer" })}
                                </Button>
                            </div>
                        </Champs>
                    </Section>
                    {rapport === null || !resume ? (
                        <EtatVide cas="premier" icone={ShieldAlert} titre={t({ en: "No attack run yet", fr: "Aucune attaque lancée" })} />
                    ) : (
                        <Section titre={t({ en: "Report", fr: "Rapport" })}>
                            <div className="flex flex-wrap items-center gap-3 pb-3 text-sm" data-resume>
                                <PointEtat etat="publie">{`${resume.a_tenu} ${t({ en: "held", fr: "ont tenu" })}`}</PointEtat>
                                <PointEtat etat={resume.a_cede ? "panne" : "fini"}>{`${resume.a_cede} ${t({ en: "got through", fr: "ont cédé" })}`}</PointEtat>
                                <PointEtat etat={resume.plausibles ? "attente" : "fini"}>{`${resume.plausibles} ${t({ en: "possible", fr: "plausibles" })}`}</PointEtat>
                                <PointEtat etat={resume.non_testees ? "attente" : "fini"}>{`${resume.non_testees} ${t({ en: "not tested", fr: "non testées" })}`}</PointEtat>
                                <Info>
                                    {t({
                                        en: "A probe not tested (no answer, no judge, a witness that went wrong, a transport failure) never counts as held.",
                                        fr: "Une sonde non testée (aucune réponse, pas de juge, témoin qui s'est mal passé, panne du transport) n'est jamais comptée comme tenue.",
                                    })}
                                </Info>
                            </div>
                            {rapport.defauts.length > 0 && (
                                <table className="w-full text-sm">
                                    <tbody className="divide-y border-t">
                                        {rapport.defauts.map((d) => (
                                            <tr key={d.id} data-defaut={d.id}>
                                                <td className="w-28 py-3">{d.gravite ? <Marque ton={d.gravite === "critique" || d.gravite === "haute" ? "danger" : "attention"}>{GRAVITE[d.gravite]}</Marque> : null}</td>
                                                <td className="py-3">
                                                    <span className="font-medium">{d.technique}</span>
                                                    {!d.confirme && <span className="ml-2 text-xs text-muted-foreground">{t({ en: "possible, not reproduced", fr: "plausible, non reproduit" })}</span>}
                                                    <span className="block text-xs text-muted-foreground">{d.raison}</span>
                                                    <span className="block text-xs">« {d.reponse} »</span>
                                                </td>
                                                <td className="w-28 py-3 text-right text-xs text-muted-foreground">
                                                    {d.couche === "plateforme" ? t({ en: "platform", fr: "plateforme" }) : d.couche === "prompt" ? "prompt" : ""}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                            {rapport.non_couvert.length > 0 && (
                                <div className="pt-4 text-xs text-muted-foreground" data-non-couvert>
                                    <p className="font-medium">{t({ en: "Not covered", fr: "Non couvert" })}</p>
                                    {rapport.non_couvert.map((l) => (
                                        <p key={l}>{l}</p>
                                    ))}
                                </div>
                            )}
                            {rapport.rejeu && (
                                <p className="pt-4 text-sm" data-rejeu>
                                    {t({ en: "Replay", fr: "Rejeu" })} : {rapport.rejeu.corriges.length} {t({ en: "fixed", fr: "corrigées" })}, {rapport.rejeu.encore_cedes.length}{" "}
                                    {t({ en: "still got through", fr: "cèdent encore" })}, {rapport.rejeu.regressions.length} {t({ en: "regressions on the sample", fr: "régressions sur l'échantillon" })}
                                </p>
                            )}
                        </Section>
                    )}
                </>
            )}
        </FenetreOnglets>
    );
}
