"use client";

/**
 * [.mark] U11 (§ 17) + partie 3, sous-lot 4 (SE-10) : « Attaquer l'agent », en deux onglets comme la maquette (Lancer, Dernier rapport).
 *
 * Lancer : le jeu d'attaques (les 15 techniques, ou le jeu public importé), la profondeur, un témoin inoffensif par attaque, les
 * essais par attaque, puis le périmètre confirmé AVANT toute sonde. Dernier rapport : une ligne par attaque (ce qu'elle a donné, comment
 * s'est passé son témoin), le contrôle du juge, ce qui a cédé, et deux gestes : « Créer un test depuis ce qui a cédé » et « Envoyer dans
 * À améliorer ». Un « non testé » n'est jamais compté comme tenu.
 *
 * Écart gardé (voir `14-ecarts-maquette.md`) : la fenêtre reste une fenêtre centrée du fork tant que le panneau de droite n'existe pas.
 */
import { Play, RotateCcw, ShieldAlert, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    creerDesTestsDepuisLesAttaquesApiV1BuilderAttaquesWorkflowIdCreerDesTestsPost,
    dernierRapportApiV1BuilderAttaquesWorkflowIdGet,
    envoyerLesAttaquesDansAAmeliorerApiV1BuilderAttaquesWorkflowIdEnvoyerAAmeliorerPost,
    importerLeJeuPublicApiV1BuilderAttaquesJeuPublicImporterPost,
    jeuPublicApiV1BuilderAttaquesJeuPublicGet,
    lancerLesAttaquesApiV1BuilderAttaquesWorkflowIdLancerPost,
    rejouerLesAttaquesApiV1BuilderAttaquesWorkflowIdRejouerPost,
} from "@/client/sdk.gen";
import type { ClasseDAttaque, EtatDuTemoin, LigneDAttaque, RapportDAttaque } from "@/components/mark/agent/publication/types";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp, Section, Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info, Marque, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";

const PROFONDEURS = ["rapide", "standard", "poussee"] as const;
const ESSAIS = ["1", "3", "5"] as const;
const TAILLE_MAX_FICHIER = 12_000_000;
type Onglet = "lancer" | "rapport";
type JeuPublic = { importe: boolean; total: number; mention?: string };

export function FenetreAttaques({ agentId, fermer }: { agentId: number; fermer: () => void }) {
    const { t } = useLangue();
    const [onglet, setOnglet] = useState<Onglet>("lancer");
    const [rapport, setRapport] = useState<RapportDAttaque | null | undefined>(undefined);
    const [jeuPublic, setJeuPublic] = useState<JeuPublic>({ importe: false, total: 0 });
    const [jeu, setJeu] = useState<"catalogue" | "public">("catalogue");
    const [profondeur, setProfondeur] = useState<(typeof PROFONDEURS)[number]>("rapide");
    const [temoin, setTemoin] = useState(true);
    const [essais, setEssais] = useState<(typeof ESSAIS)[number]>("3");
    const [confirme, setConfirme] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState(false);
    const fichier = useRef<HTMLInputElement>(null);

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
    const CLASSE: Record<ClasseDAttaque, string> = {
        a_tenu: t({ en: "held", fr: "a tenu" }),
        a_cede: t({ en: "got through", fr: "a cédé" }),
        plausible: t({ en: "possible", fr: "plausible" }),
        non_teste: t({ en: "not tested", fr: "non testé" }),
    };
    const TEMOIN: Record<EtatDuTemoin, string> = {
        normal: t({ en: "answers normally", fr: "répond normalement" }),
        anormal: t({ en: "went wrong", fr: "s'est mal passé" }),
        sans: "–",
        non_juge: t({ en: "not judged", fr: "non jugé" }),
    };
    const LIBELLE_CATALOGUE = t({ en: "The 15 techniques (catalogue)", fr: "Les 15 techniques (catalogue)" });
    const LIBELLE_PUBLIC = jeuPublic.importe
        ? t({ en: `Public set, ${jeuPublic.total} attacks (MIT license)`, fr: `Jeu public, ${jeuPublic.total} attaques (licence MIT)` })
        : t({ en: "Public set (not imported yet)", fr: "Jeu public (pas encore importé)" });

    const charger = useCallback(async () => {
        // Les deux lectures partent ensemble : le rapport et l'état du jeu public.
        const [r, p] = await Promise.all([
            dernierRapportApiV1BuilderAttaquesWorkflowIdGet({ path: { workflow_id: agentId } }),
            jeuPublicApiV1BuilderAttaquesJeuPublicGet(),
        ]);
        if (r.error) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setRapport(((r.data as { rapport?: RapportDAttaque | null } | undefined)?.rapport ?? null) as RapportDAttaque | null);
        if (!p.error && p.data) setJeuPublic(p.data as unknown as JeuPublic);
    }, [agentId]);
    useEffect(() => {
        void charger();
    }, [charger]);

    const lancer = async () => {
        if (!confirme || enCours) return;
        setEnCours(true);
        const r = await lancerLesAttaquesApiV1BuilderAttaquesWorkflowIdLancerPost({
            path: { workflow_id: agentId },
            body: { profondeur, confirme: true, modifie_l_environnement: false, corrige: false, essais: Number(essais), temoin, jeu },
        });
        setEnCours(false);
        if (r.error) {
            notifier.echec({ fr: "Attaque impossible. Réessayez.", en: "Could not run the attack. Try again." }, { erreur: r.error, reessayer: () => void lancer() });
            return;
        }
        setRapport((r.data as { rapport: RapportDAttaque }).rapport);
        setOnglet("rapport");
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

    const importer = async (f: File | undefined) => {
        if (!f) return;
        if (f.size > TAILLE_MAX_FICHIER) {
            notifier.avertissement({ fr: "Fichier trop gros (12 Mo au plus).", en: "File too large (12 MB at most)." });
            return;
        }
        setEnCours(true);
        const r = await importerLeJeuPublicApiV1BuilderAttaquesJeuPublicImporterPost({ body: { contenu: await f.text() } });
        setEnCours(false);
        if (fichier.current) fichier.current.value = "";
        if (r.error) {
            notifier.echec({ fr: "Import impossible. Vérifiez le fichier (CSV avec une colonne prompt).", en: "Could not import. Check the file (CSV with a prompt column)." }, { erreur: r.error });
            return;
        }
        const fait = r.data as unknown as { ajoutees: number; deja_la: number; total: number };
        notifier.succes({
            fr: fait.ajoutees ? `${fait.ajoutees} attaques ajoutées (${fait.total} au total).` : "Rien de nouveau : toutes les attaques étaient déjà là.",
            en: fait.ajoutees ? `${fait.ajoutees} attacks added (${fait.total} in all).` : "Nothing new: every attack was already there.",
        });
        setJeuPublic({ importe: true, total: fait.total });
        setJeu("public");
    };

    const suite = async (geste: "tests" | "ameliorer") => {
        if (enCours) return;
        setEnCours(true);
        const r =
            geste === "tests"
                ? await creerDesTestsDepuisLesAttaquesApiV1BuilderAttaquesWorkflowIdCreerDesTestsPost({ path: { workflow_id: agentId }, body: {} })
                : await envoyerLesAttaquesDansAAmeliorerApiV1BuilderAttaquesWorkflowIdEnvoyerAAmeliorerPost({ path: { workflow_id: agentId }, body: {} });
        setEnCours(false);
        if (r.error) {
            notifier.echec(
                geste === "tests"
                    ? { fr: "Création des tests impossible. Réessayez.", en: "Could not create the tests. Try again." }
                    : { fr: "Envoi impossible. Réessayez.", en: "Could not send. Try again." },
                { erreur: r.error, reessayer: () => void suite(geste) },
            );
            return;
        }
        if (geste === "tests") {
            const fait = r.data as unknown as { crees: unknown[]; deja: unknown[]; refuses: unknown[] };
            if (fait.refuses.length)
                notifier.avertissement({
                    fr: `${fait.crees.length} test(s) créé(s), ${fait.refuses.length} refusé(s) : ils gardaient des données qui semblent réelles.`,
                    en: `${fait.crees.length} test(s) created, ${fait.refuses.length} refused: they held data that looks real.`,
                });
            else if (!fait.crees.length)
                notifier.information({ fr: "Les tests existent déjà. Retrouvez-les dans Tests, dossier Attaques.", en: "The tests already exist. Find them in Tests, folder Attacks." });
            else notifier.succes({ fr: `${fait.crees.length} test(s) créé(s) dans le dossier Attaques.`, en: `${fait.crees.length} test(s) created in the Attacks folder.` });
        } else {
            const fait = r.data as unknown as { envoyes: unknown[]; echecs: unknown[] };
            if (fait.echecs.length) notifier.avertissement({ fr: `${fait.envoyes.length} envoyée(s), ${fait.echecs.length} non rangée(s). Réessayez.`, en: `${fait.envoyes.length} sent, ${fait.echecs.length} not filed. Try again.` });
            else notifier.succes({ fr: `${fait.envoyes.length} problème(s) envoyé(s) dans À améliorer.`, en: `${fait.envoyes.length} problem(s) sent to To improve.` });
        }
    };

    const resume = rapport?.resume;
    const aCede = rapport?.defauts.some((d) => d.confirme) ?? false;
    const peutLancer = confirme && !enCours && (jeu === "catalogue" || jeuPublic.importe);

    const lancerOnglet = (
        <>
            <Section
                titre={t({ en: "Scope", fr: "Périmètre" })}
                info={t({
                    en: "Confirmed before any probe, and never widened during the run. The depth sets the number of probes.",
                    fr: "Confirmé avant toute sonde, jamais élargi en cours de route. La profondeur fixe le nombre de sondes.",
                })}
            >
                <Champs>
                    <LigneChamp
                        libelle={t({ en: "Attack set", fr: "Jeu d'attaques" })}
                        info={t({
                            en: "The 15 techniques of the catalogue, or the public set you import (a CSV file, MIT license). Nothing is translated by a model here.",
                            fr: "Les 15 techniques du catalogue, ou le jeu public que vous importez (un fichier CSV, licence MIT). Rien n'est traduit par un modèle ici.",
                        })}
                    >
                        <span className="flex items-center gap-2">
                            <Liste
                                className="w-72"
                                valeur={jeu}
                                changer={(v) => setJeu(v === "public" ? "public" : "catalogue")}
                                options={[
                                    { valeur: "catalogue", libelle: LIBELLE_CATALOGUE },
                                    { valeur: "public", libelle: LIBELLE_PUBLIC },
                                ]}
                            />
                            <input ref={fichier} type="file" accept=".csv,text/csv" hidden aria-label={t({ en: "Public set file", fr: "Fichier du jeu public" })} onChange={(e) => void importer(e.target.files?.[0])} />
                            <Button variant="outline" size="sm" disabled={enCours} onClick={() => fichier.current?.click()}>
                                <Upload className="size-4" /> {t({ en: "Import", fr: "Importer" })}
                            </Button>
                        </span>
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Depth", fr: "Profondeur" })}>
                        <Segmente valeur={NOM[profondeur]} options={PROFONDEURS.map((p) => NOM[p])} changer={(v) => setProfondeur(PROFONDEURS.find((p) => NOM[p] === v) ?? "rapide")} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Attacks translated too", fr: "Attaques traduites aussi" })}
                        info={t({
                            en: "Not available yet: translating the attacks calls a model, so it waits for a go. A protection that only holds in French does not hold.",
                            fr: "Pas encore disponible : traduire les attaques appelle un modèle, donc attend un accord. Une protection qui ne tient qu'en français ne tient pas.",
                        })}
                    >
                        <Switch checked={false} disabled aria-label={t({ en: "Attacks translated too", fr: "Attaques traduites aussi" })} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "A harmless witness per attack", fr: "Un témoin inoffensif par attaque" })}
                        info={t({
                            en: "Right after the attack, a normal request: the agent must still answer it. An agent that shuts down on everything does not « hold », it is broken. The judge is also checked on a normal request, to prove it does not cry wolf.",
                            fr: "Juste après l'attaque, une demande normale : l'agent doit encore y répondre. Un agent qui se ferme à tout ne « tient » pas, il est cassé. Le juge est aussi vérifié sur une demande normale, pour prouver qu'il ne crie pas au loup.",
                        })}
                    >
                        <Switch checked={temoin} onCheckedChange={setTemoin} aria-label={t({ en: "A harmless witness per attack", fr: "Un témoin inoffensif par attaque" })} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Tries per attack", fr: "Essais par attaque" })}
                        info={t({
                            en: "A failure is replayed this many times on fresh sessions before it is confirmed. One that gives way once in three has given way.",
                            fr: "Un échec est rejoué autant de fois sur des sessions neuves avant d'être confirmé. Une attaque qui cède une fois sur trois a cédé.",
                        })}
                    >
                        <Segmente valeur={essais} options={[...ESSAIS]} changer={(v) => setEssais(ESSAIS.find((e) => e === v) ?? "3")} />
                    </LigneChamp>
                    <div className="flex items-center gap-3 py-3 text-sm">
                        <Checkbox id="confirme-attaque" checked={confirme} onCheckedChange={(c) => setConfirme(c === true)} />
                        <label htmlFor="confirme-attaque" className="flex-1 cursor-pointer">
                            {t({
                                en: "I confirm this scope: the agent is attacked as it is, its environment is not changed, the report alone.",
                                fr: "Je confirme ce périmètre : l'agent est attaqué tel qu'il est, son environnement n'est pas modifié, rapport seul.",
                            })}
                        </label>
                    </div>
                </Champs>
            </Section>
        </>
    );

    const rapportOnglet =
        rapport === null || !resume || !rapport ? (
            <EtatVide cas="premier" icone={ShieldAlert} titre={t({ en: "No attack run yet", fr: "Aucune attaque lancée" })} />
        ) : (
            <>
                <p className="pb-2 text-sm text-muted-foreground" data-resume>
                    {rapport.version != null ? `${t({ en: "Draft", fr: "Brouillon" })} v${rapport.version} · ` : ""}
                    <DateRelative valeur={rapport.le} /> · {resume.jouees} {t({ en: "attacks", fr: "attaques" })}
                </p>
                <div className="flex flex-wrap items-center gap-3 pb-3 text-sm">
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
                {rapport.controle_du_juge?.ok === false && (
                    <p className="pb-3 text-sm" data-juge-suspect role="alert">
                        <Marque ton="attention">{t({ en: "Judge to check", fr: "Juge à vérifier" })}</Marque>{" "}
                        {t({
                            en: "The judge saw an attack in a harmless request: read the « got through » verdicts of this run with care.",
                            fr: "Le juge a vu une attaque dans une demande normale : lisez avec prudence les « a cédé » de ce passage.",
                        })}
                    </p>
                )}
                {rapport.lignes && rapport.lignes.length > 0 && (
                    <table className="w-full text-sm" data-lignes>
                        <thead className="border-b text-xs text-muted-foreground">
                            <tr>
                                <th className="py-2 text-left font-normal">{t({ en: "Attack", fr: "Attaque" })}</th>
                                <th className="pl-4 text-left font-normal">{t({ en: "Family", fr: "Famille" })}</th>
                                <th className="pl-4 text-left font-normal">{t({ en: "Result", fr: "Résultat" })}</th>
                                <th className="pl-4 text-left font-normal">{t({ en: "Witness", fr: "Témoin" })}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y">
                            {rapport.lignes.map((l: LigneDAttaque) => (
                                <tr key={l.id} data-ligne={l.id}>
                                    <td className="py-3">{l.attaque}</td>
                                    <td className="pl-4 text-muted-foreground">{l.origine === "conflit" ? t({ en: "Rule conflict", fr: "Conflit entre règles" }) : (l.famille ?? l.technique)}</td>
                                    <td className="pl-4 whitespace-nowrap">
                                        <PointEtat etat={l.classe === "a_tenu" ? "publie" : l.classe === "a_cede" ? "panne" : l.classe === "plausible" ? "attente" : "fini"}>{CLASSE[l.classe]}</PointEtat>
                                    </td>
                                    <td className="pl-4 text-muted-foreground">{TEMOIN[l.temoin]}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                <div className="flex gap-2 pt-4">
                    <Button variant="outline" size="sm" disabled={!aCede || enCours} onClick={() => void suite("tests")}>
                        {t({ en: "Create a test from what got through", fr: "Créer un test depuis ce qui a cédé" })}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={!aCede || enCours} onClick={() => void suite("ameliorer")}>
                        {t({ en: "Send to To improve", fr: "Envoyer dans À améliorer" })}
                    </Button>
                </div>
                {rapport.defauts.length > 0 && (
                    <div className="pt-6">
                        <p className="pb-1 text-xs font-medium tracking-wider text-muted-foreground uppercase">{t({ en: "What got through", fr: "Ce qui a cédé" })}</p>
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
                    </div>
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
            </>
        );

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
            onglets={[t({ en: "Launch", fr: "Lancer" }), t({ en: "Last report", fr: "Dernier rapport" })]}
            onglet={onglet === "lancer" ? t({ en: "Launch", fr: "Lancer" }) : t({ en: "Last report", fr: "Dernier rapport" })}
            changerOnglet={(o) => setOnglet(o === t({ en: "Launch", fr: "Lancer" }) ? "lancer" : "rapport")}
            valider={null}
            pied={
                onglet === "lancer" ? (
                    <Button disabled={!peutLancer} onClick={() => void lancer()}>
                        <Play className="size-4" />
                        {enCours ? t({ en: "Attacking…", fr: "Attaque en cours…" }) : t({ en: "Launch the attacks", fr: "Lancer les attaques" })}
                    </Button>
                ) : (
                    rapport && (
                        <Button variant="outline" disabled={enCours} onClick={() => void rejouer()}>
                            <RotateCcw className="size-4" /> {t({ en: "Replay the failures", fr: "Rejouer les échecs" })}
                        </Button>
                    )
                )
            }
        >
            {erreur ? <EtatVide cas="erreur" reessayer={() => void charger()} /> : rapport === undefined ? <EtatVide cas="chargement" lignes={4} /> : onglet === "lancer" ? lancerOnglet : rapportOnglet}
        </FenetreOnglets>
    );
}
