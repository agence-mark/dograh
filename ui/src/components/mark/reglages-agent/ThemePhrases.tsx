"use client";

/**
 * [.mark] Theme « Phrases » (chantier fiabilite-orchestration, lot 4 bis ; REFAIT au lot 5 de correctifs-apres-banc-v4,
 * maquette retenue par Evan sur la branche `maquette/phrases-du-code`).
 *
 * Tout ce que le CODE dit de lui-même, sans le modèle, vient d'une règle (`phrases_regles`, `ReglePhrase`) : un motif
 * que le code sait détecter (`phrases/catalogue-des-phrases.json`, copie de `api/services/phrases/catalogue.py`,
 * gardée égale par un test), un endroit (tout le groupe, cet agent, une étape), une à trois phrases, un délai, des
 * redites, un plafond, une sortie. L'appel prend la règle de l'étape, sinon de l'agent, sinon du groupe, sinon le défaut.
 *
 * L'écran : une notice, des filtres par moment avec compteurs, la pause minimale (`phrases_repos_s`), UNE CARTE PAR
 * RÈGLE (interrupteur, origine, dernière fois dite) qui ouvre sa modale, « Ajouter une phrase » en deux étapes, et,
 * sur le principal d'un groupe, la vue du groupe (motif × agent). Un spécialisé voit en lecture les règles du groupe
 * héritées et choisit : « Remplacer dans cet agent » ou « Modifier sur le principal ».
 *
 * Reprise (F17) : la phrase pont (`attente.phrase_pont`, son délai) et la phrase avant un transfert
 * (`transfert_humain.phrase_mise_en_relation`), réglées avant ce thème, s'y montrent comme règles du groupe ; le
 * premier enregistrement les écrit comme règles et retire les anciennes clés (valeurs gardées).
 */
import { MessageSquareText, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ReglePhrase, WorkflowConfigurations } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { Theme } from "../ecran/Theme";
import { useGroupe } from "../groupe/contexte-groupe";
import { DELAI_PHRASE_PONT_DEFAUT_S } from "../groupe/reglages-groupe";
import { type Texte, useLangue } from "../langue/langue";
import { useEnregistrementTheme } from "./enregistrement";
import { CartePhrase } from "./phrases/CartePhrase";
import { type Dernier, useCarte, useDestinations, useEquipe, useOutilsDeLAgent } from "./phrases/donnees";
import { type LigneDeListe,lignesDeLaListe } from "./phrases/liste";
import { ModaleAjout } from "./phrases/ModaleAjout";
import { type EnvironnementPhrases, ModaleRegle } from "./phrases/ModaleRegle";
import {
    ALIAS_DE_MOTIFS,
    BORNES_PHRASES,
    chargeRegle,
    cleDeRegle,
    type ContextePhrases,
    type Endroit,
    erreursDesPhrases as erreursDesRegles,
    type EtapeGraphe,
    type Moment,
    MOMENTS,
    MOTIF_MISE_EN_RELATION,
    MOTIF_PASSATION,
    MOTIFS_DE_PHRASES,
    nomDeLEtape,
    normaliserRegle,
    REPOS_DEFAUT_S,
} from "./phrases/modele";
import { NoticePhrases } from "./phrases/NoticePhrases";
import { PhrasesEnLecture } from "./phrases/PhrasesEnLecture";
import { VueDuGroupe } from "./phrases/VueDuGroupe";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export { BORNES_PHRASES, MOTIFS_DE_PHRASES };
export type { MotifDePhrase } from "./phrases/modele";

export const ID_THEME_PHRASES = "phrases";
export const TITRE_PHRASES = { en: "Phrases", fr: "Phrases" };

/** Ce que le thème tient en brouillon : les règles et la pause minimale (saisie, vide = 3 s). */
export interface BrouillonPhrases {
    regles: ReglePhrase[];
    repos: string;
}

/** Les règles de la configuration, plus les anciennes phrases reprises comme règles de groupe (F17). */
export const extrairePhrases = (c: Partial<WorkflowConfigurations>): BrouillonPhrases => {
    const regles = (c.phrases_regles ?? []).map(normaliserRegle);
    const aUneRegleDeGroupe = (motif: string) => regles.some((r) => r.motif === motif && r.portee === "groupe");
    const pont = c.attente?.phrase_pont?.trim() ?? "";
    if (pont !== "" && !aUneRegleDeGroupe(MOTIF_PASSATION)) {
        regles.push(
            normaliserRegle({
                motif: MOTIF_PASSATION,
                portee: "groupe",
                variantes: [pont],
                delai_s: c.attente?.delai_phrase_pont_s ?? DELAI_PHRASE_PONT_DEFAUT_S,
                active: true,
            }),
        );
    }
    const relation = c.transfert_humain?.phrase_mise_en_relation?.trim() ?? "";
    if (relation !== "" && !aUneRegleDeGroupe(MOTIF_MISE_EN_RELATION)) {
        regles.push(normaliserRegle({ motif: MOTIF_MISE_EN_RELATION, portee: "groupe", variantes: [relation], active: true }));
    }
    return { regles, repos: c.phrases_repos_s === null || c.phrases_repos_s === undefined ? "" : String(c.phrases_repos_s) };
};

/** Ce qui est enregistré : les règles, nettoyées, dans la forme du serveur (aucune clé perdue). */
export const chargePhrases = (regles: ReglePhrase[], etapes: EtapeGraphe[] = []): ReglePhrase[] => regles.map((r) => chargeRegle(r, etapes));

/** Les erreurs nommées des règles ; la pause minimale en plus (1 à 10 s). */
export const erreursDesPhrases = (regles: ReglePhrase[], etapes: EtapeGraphe[] = [], repos = "") => {
    const erreurs = erreursDesRegles(regles, etapes);
    const n = repos.trim() === "" ? null : Number(repos.replace(",", "."));
    if (n !== null && (!Number.isFinite(n) || n < 1 || n > 10)) {
        erreurs.push({
            cle: "phrases_repos_s",
            libelle: { en: "Minimum pause between two waiting sentences", fr: "Pause minimale entre deux phrases d'attente" },
            message: { en: "Between 1 and 10 s.", fr: "Entre 1 et 10 s." },
        });
    }
    return erreurs;
};

const TEXTES = {
    description: {
        en: "What the voice says by itself, without the model, when something waits or fails.",
        fr: "Ce que la voix dit d'elle-même, sans le modèle, quand on attend ou quand quelque chose échoue.",
    },
    toutes: { en: "All", fr: "Toutes" },
    attentes: { en: "Waits", fr: "Attentes" },
    problemes: { en: "Problems", fr: "Problèmes" },
    actions: { en: "Actions", fr: "Actions" },
    pause: { en: "Minimum pause between two waiting sentences", fr: "Pause minimale entre deux phrases d'attente" },
    pauseAide: {
        en: "One waiting sentence at a time; after it, the code stays quiet at least this long (1 to 10 s). Empty: 3 s. Set on the main agent.",
        fr: "Une seule phrase d'attente à la fois ; après elle, le code se tait au moins ce temps (1 à 10 s). Vide : 3 s. Réglée sur l'agent principal.",
    },
    ajouter: { en: "Add a sentence", fr: "Ajouter une phrase" },
    reprise: {
        en: "Taken over from the former setting: saved as a rule at the next save of this theme.",
        fr: "Repris de l'ancien réglage : enregistré comme règle au prochain enregistrement de ce thème.",
    },
    regleDuGroupe: { en: "Group rule, set on the main agent: read only here.", fr: "Règle du groupe, réglée sur le principal : en lecture ici." },
    remplacee: { en: "Replaced in this agent by its own rule.", fr: "Remplacée dans cet agent par sa propre règle." },
    remplacer: { en: "Replace in this agent", fr: "Remplacer dans cet agent" },
    modifierSurLePrincipal: { en: "Edit on the main agent", fr: "Modifier sur le principal" },
    jamais: { en: "never said in the recent calls", fr: "jamais dite dans les derniers appels" },
    aucune: { en: "No rule matches this filter.", fr: "Aucune règle pour ce filtre." },
} satisfies Record<string, Texte>;

const MOMENT_TITRE: Record<Moment, { titre: Texte; aide: Texte }> = {
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
        aide: { en: "Said right before the code acts.", fr: "Dites juste avant que le code agisse." },
    },
};

type Ouverte = { index: number } | { nouvelle: ReglePhrase };

const lireN = (texte: string): number | null => {
    if (texte.trim() === "") return null;
    const n = Number(texte.replace(",", "."));
    return Number.isFinite(n) ? n : null;
};

export const ThemePhrases = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    etapes,
    outilsUuids = [],
    workflowId,
}: ProprietesThemeAgent & { etapes: EtapeGraphe[]; outilsUuids?: string[]; workflowId?: number }) => {
    const { t, langue } = useLangue();
    const groupe = useGroupe();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extrairePhrases);
    const { afficher } = useRevelation(ouvrir);
    const regles = brouillon.regles;
    const setRegles = (maj: (avant: ReglePhrase[]) => ReglePhrase[]) => setBrouillon((avant) => ({ ...avant, regles: maj(avant.regles) }));

    const [version, setVersion] = useState(0);
    const [filtre, setFiltre] = useState<"tout" | Moment>("tout");
    const [ouverte, setOuverte] = useState<Ouverte | null>(null);
    const [ajout, setAjout] = useState<{ motif: string | null; endroit: Endroit } | null>(null);

    // « Ajouter » depuis les réglages d'un autre agent (vue du groupe) : `?phrases_ajout=<motif>`.
    useEffect(() => {
        const motif = new URLSearchParams(window.location.search).get("phrases_ajout");
        if (!motif) return;
        const connu = MOTIFS_DE_PHRASES.some((m) => m.id === (ALIAS_DE_MOTIFS[motif] ?? motif));
        if (!connu) return;
        ouvrir();
        setAjout({ motif, endroit: { portee: "agent" } });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const modifie = differe(brouillon, enregistre);
    const erreurs = erreursDesPhrases(regles, etapes, brouillon.repos);
    useEtatTheme(ID_THEME_PHRASES, modifie, erreurs.length > 0);

    const specialise = groupe.specialiseDe !== null;
    // Les règles du groupe vivent sur le principal seulement (un agent seul a « cet agent »).
    const peutRegleDeGroupe = !specialise && Array.isArray(resolue.agents_specialises);
    const estPrincipal = peutRegleDeGroupe;
    const ancienPont = (resolue.attente?.phrase_pont ?? "").trim() !== "" || resolue.attente?.delai_phrase_pont_s != null;
    const ancienneRelation = (resolue.transfert_humain?.phrase_mise_en_relation ?? "").trim() !== "";

    const { carte, erreur: carteIllisible } = useCarte(workflowId, ouvert, version);
    const outils = useOutilsDeLAgent(outilsUuids, ouvert);
    const equipe = useEquipe(ouvert);
    const destinations = useDestinations(equipe);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_PHRASES,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Phrases", fr: "Phrases" },
                modifie,
                config: () => {
                    const charge: Partial<WorkflowConfigurations> = {};
                    // Les règles : écrites si elles ont changé, ou si la clé existe déjà (une pause seule ne touche pas aux règles).
                    if (differe(regles, enregistre.regles) || resolue.phrases_regles != null || ancienPont || ancienneRelation) {
                        charge.phrases_regles = chargePhrases(regles, etapes);
                    }
                    // La pause : n'écrit la clé que si elle est posée ou déjà là (une config qui n'y touche pas reste inchangée).
                    const repos = lireN(brouillon.repos);
                    if (repos !== null || resolue.phrases_repos_s !== undefined) charge.phrases_repos_s = repos;
                    // F17 : les anciennes clés sont retirées une fois leur valeur devenue règle (gardée par le thème).
                    if (ancienPont) {
                        const { phrase_pont: _p, delai_phrase_pont_s: _d, ...reste } = resolue.attente ?? {};
                        charge.attente = reste;
                    }
                    if (ancienneRelation) {
                        const { phrase_mise_en_relation: _r, ...reste } = resolue.transfert_humain ?? {};
                        charge.transfert_humain = reste;
                    }
                    return charge;
                },
                apres: () => {
                    resynchroniser();
                    setVersion((v) => v + 1);
                },
            },
        ],
    });

    const reposS = lireN(brouillon.repos) ?? REPOS_DEFAUT_S;
    const maxOutil = (() => {
        const delais = outils.map((o) => o.delaiTotalS).filter((d): d is number => d !== null);
        return delais.length > 0 ? Math.max(...delais) : null;
    })();
    const contexte: ContextePhrases = useMemo(
        () => ({
            langue,
            t,
            reposS,
            abandonS: { outil: maxOutil, travail: resolue.travail_delai_max_s ?? 60, garde: resolue.delai_garde_modele_s ?? null },
            rythme: { delaiS: resolue.max_user_idle_timeout, relances: resolue.user_idle_max_prompts ?? 0 },
            destinations,
        }),
        [langue, t, reposS, maxOutil, resolue.travail_delai_max_s, resolue.delai_garde_modele_s, resolue.max_user_idle_timeout, resolue.user_idle_max_prompts, destinations],
    );
    const env: EnvironnementPhrases = useMemo(
        () => ({
            etapes,
            outils,
            champsFiche: (resolue.fiche_champs ?? []).map((c) => ({ nom: c.nom, valeurs: c.valeurs ?? null })),
            equipe,
            peutGroupe: peutRegleDeGroupe,
            contexte,
        }),
        [etapes, outils, resolue.fiche_champs, equipe, peutRegleDeGroupe, contexte],
    );

    const agentDeLaCarte = carte?.agents.find((a) => a.id === workflowId);
    const heritees = useMemo(() => (specialise ? (agentDeLaCarte?.regles_du_groupe ?? []) : []), [specialise, agentDeLaCarte]);
    const lignes = useMemo(() => lignesDeLaListe(regles, heritees, etapes), [regles, heritees, etapes]);
    const compte = (m: Moment) => lignes.filter((l) => l.motif.moment === m).length;
    const visibles = lignes.filter((l) => filtre === "tout" || l.motif.moment === filtre);
    const allumees = lignes.filter((l) => l.active && !l.remplacee).length;

    const reprise = (r: ReglePhrase) =>
        r.portee === "groupe" &&
        !(resolue.phrases_regles ?? []).some((x) => x.motif === r.motif && (x.portee ?? "agent") === "groupe") &&
        ((r.motif === MOTIF_PASSATION && ancienPont) || (r.motif === MOTIF_MISE_EN_RELATION && ancienneRelation));

    const dernierDe = (ligne: LigneDeListe): string => {
        const trouve: Dernier | null | undefined = ligne.defaut || ligne.heritee
            ? agentDeLaCarte?.motifs.find((m) => m.motif === ligne.motif.id)?.dernier
            : agentDeLaCarte?.regles?.find((r) => cleDeRegle(r) === cleDeRegle(ligne.regle))?.dernier;
        if (!trouve || trouve.run == null) return t(TEXTES.jamais);
        const date = trouve.moment ? new Date(trouve.moment.replace(" ", "T")) : null;
        const quand = date && !Number.isNaN(date.getTime()) ? date.toLocaleString(langue === "fr" ? "fr-FR" : "en-GB", { dateStyle: "short", timeStyle: "short" }) : (trouve.moment ?? "").slice(0, 16);
        return `${t({ en: "last said", fr: "dite le" })} ${quand}`;
    };

    const basculer = (ligne: LigneDeListe, active: boolean) => {
        if (ligne.index !== null) {
            setRegles((avant) => avant.map((r, i) => (i === ligne.index ? { ...r, active } : r)));
        } else if (ligne.defaut) {
            // Allumer ou éteindre un défaut pose une règle de cet agent qui porte les valeurs du catalogue.
            setRegles((avant) => [...avant, { ...ligne.regle, active }]);
        }
    };

    const ouvrirLaLigne = (ligne: LigneDeListe) => {
        if (ligne.index !== null) setOuverte({ index: ligne.index });
        else setOuverte({ nouvelle: { ...ligne.regle, active: ligne.defaut ? true : ligne.regle.active } });
    };

    /** La case du principal dans la vue du groupe : sa règle (de cet agent, sinon du groupe), sinon l'ajout du motif. */
    const ouvrirLeMotif = (motif: string) => {
        const index = regles.findIndex((r) => r.motif === motif && r.portee === "agent" && (r.outils ?? []).length === 0);
        const indexGroupe = regles.findIndex((r) => r.motif === motif && r.portee === "groupe");
        const trouve = index >= 0 ? index : indexGroupe;
        if (trouve >= 0) setOuverte({ index: trouve });
        else setAjout({ motif, endroit: { portee: peutRegleDeGroupe ? "groupe" : "agent" } });
    };

    const remplacerDansCetAgent = (ligne: LigneDeListe) =>
        setOuverte({ nouvelle: { ...ligne.regle, portee: "agent", etape: null, etape_id: null } });

    const existeUneRegleDuGroupe = (r: ReglePhrase) => r.portee !== "groupe" && (specialise ? heritees.some((h) => h.motif === r.motif) : regles.some((x) => x.motif === r.motif && x.portee === "groupe"));

    return (
        <Theme
            id={ID_THEME_PHRASES}
            icone={MessageSquareText}
            titre={TITRE_PHRASES}
            description={TEXTES.description}
            resume={[
                `${lignes.filter((l) => !l.defaut).length} ${t({ en: "rule(s)", fr: "règle(s)" })}`,
                `${allumees}/${lignes.length} ${t({ en: "on", fr: "allumées" })}`,
                `${t({ en: "pause", fr: "pause" })} ${lireN(brouillon.repos) ?? REPOS_DEFAUT_S} s`,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <NoticePhrases />

            <div className="flex flex-wrap items-end justify-between gap-3">
                <Tabs value={filtre} onValueChange={(v) => setFiltre(v as typeof filtre)}>
                    <TabsList>
                        <TabsTrigger value="tout">{`${t(TEXTES.toutes)} (${lignes.length})`}</TabsTrigger>
                        <TabsTrigger value="attente">{`${t(TEXTES.attentes)} (${compte("attente")})`}</TabsTrigger>
                        <TabsTrigger value="probleme">{`${t(TEXTES.problemes)} (${compte("probleme")})`}</TabsTrigger>
                        <TabsTrigger value="action">{`${t(TEXTES.actions)} (${compte("action")})`}</TabsTrigger>
                    </TabsList>
                </Tabs>
                <Button onClick={() => setAjout({ motif: null, endroit: { portee: "agent" } })}>
                    <Plus className="h-4 w-4" /> {t(TEXTES.ajouter)}
                </Button>
            </div>

            <ChampReglage
                cle="phrases_repos_s"
                idControle="phrases_repos_s"
                libelle={TEXTES.pause}
                aides={[TEXTES.pauseAide]}
                bornes={{ en: `≥ ${1} · ≤ ${10} · optional`, fr: `≥ ${1} · ≤ ${10} · facultatif` }}
                disposition="ligne"
            >
                <div className="flex items-center gap-2">
                    <Input
                        id="phrases_repos_s"
                        type="number"
                        inputMode="decimal"
                        className="w-20"
                        min={1}
                        max={10}
                        step="0.5"
                        disabled={specialise}
                        placeholder={String(REPOS_DEFAUT_S)}
                        value={brouillon.repos}
                        onChange={(e) => setBrouillon((avant) => ({ ...avant, repos: e.target.value }))}
                    />
                    <span className="text-sm text-muted-foreground">s</span>
                </div>
            </ChampReglage>

            <ChampReglage
                cle="phrases_regles"
                libelle={{ en: "Rules of the sentences said by the code", fr: "Règles des phrases dites par le code" }}
                aides={[
                    {
                        en: "For each cause: the step's rule, else this agent's, else the main agent's group rule, else the default. A specialised agent takes the main agent's sentence until it sets its own.",
                        fr: "Pour chaque motif : la règle de l'étape, sinon celle de cet agent, sinon la règle de groupe du principal, sinon le défaut. Un spécialisé reprend la phrase du principal tant qu'il n'a pas la sienne.",
                    },
                ]}
            >
                <div className="space-y-5">
                    {MOMENTS.filter((m) => visibles.some((l) => l.motif.moment === m)).map((moment) => (
                        <div key={moment} className="space-y-2" data-moment={moment}>
                            <div>
                                <h3 className="text-sm font-semibold">{t(MOMENT_TITRE[moment].titre)}</h3>
                                <p className="text-xs text-muted-foreground">{t(MOMENT_TITRE[moment].aide)}</p>
                            </div>
                            {visibles
                                .filter((l) => l.motif.moment === moment)
                                .map((ligne) => (
                                    <CartePhrase
                                        key={ligne.id + (ligne.index ?? "")}
                                        id={ligne.id}
                                        regle={ligne.regle}
                                        motif={ligne.motif}
                                        origine={ligne.origine}
                                        contexte={contexte}
                                        etape={ligne.regle.portee === "etape" ? nomDeLEtape(ligne.regle, etapes) : undefined}
                                        supprimee={ligne.supprimee}
                                        active={ligne.active}
                                        derniere={dernierDe(ligne)}
                                        lecture={ligne.heritee}
                                        onOuvrir={() => ouvrirLaLigne(ligne)}
                                        onBasculer={ligne.heritee ? undefined : (active) => basculer(ligne, active)}
                                        pied={
                                            ligne.index !== null && reprise(ligne.regle) ? (
                                                <p className="text-xs text-muted-foreground" data-note="phrase-reprise">
                                                    {t(TEXTES.reprise)}
                                                </p>
                                            ) : ligne.heritee ? (
                                                <div
                                                    className="flex flex-wrap items-center gap-2 rounded-md border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
                                                    data-note="regle-heritee"
                                                >
                                                    <span>{t(ligne.remplacee ? TEXTES.remplacee : TEXTES.regleDuGroupe)}</span>
                                                    {!ligne.remplacee && (
                                                        <Button variant="outline" size="sm" className="ml-auto h-7" onClick={() => remplacerDansCetAgent(ligne)}>
                                                            {t(TEXTES.remplacer)}
                                                        </Button>
                                                    )}
                                                    <Link href={`/workflow/${groupe.specialiseDe}/settings`} className="inline-flex h-7 items-center rounded-md px-2 underline">
                                                        {t(TEXTES.modifierSurLePrincipal)}
                                                    </Link>
                                                </div>
                                            ) : undefined
                                        }
                                    />
                                ))}
                        </div>
                    ))}
                    {visibles.length === 0 && <p className="text-xs text-muted-foreground">{t(TEXTES.aucune)}</p>}
                </div>
            </ChampReglage>

            {estPrincipal && workflowId !== undefined && (
                <VueDuGroupe carte={carte} workflowId={workflowId} onOuvrir={ouvrirLeMotif} onAjouterPropre={(motif) => setAjout({ motif, endroit: { portee: "agent" } })} />
            )}

            {workflowId !== undefined && ouvert && <PhrasesEnLecture carte={carte} erreur={carteIllisible} workflowId={workflowId} />}

            {ouverte && "index" in ouverte && regles[ouverte.index] && (
                <ModaleRegle
                    key={`regle-${ouverte.index}`}
                    regle={regles[ouverte.index]}
                    env={env}
                    peutSupprimer
                    existeUneRegleDuGroupe={existeUneRegleDuGroupe(regles[ouverte.index])}
                    onEnregistrer={(r) => {
                        setRegles((avant) => avant.map((x, i) => (i === ouverte.index ? r : x)));
                        setOuverte(null);
                    }}
                    onSupprimer={() => {
                        setRegles((avant) => avant.filter((_, i) => i !== ouverte.index));
                        setOuverte(null);
                    }}
                    onFermer={() => setOuverte(null)}
                />
            )}
            {ouverte && "nouvelle" in ouverte && (
                <ModaleRegle
                    key={`nouvelle-${ouverte.nouvelle.motif}-${ouverte.nouvelle.portee}`}
                    regle={ouverte.nouvelle}
                    env={env}
                    existeUneRegleDuGroupe={existeUneRegleDuGroupe(ouverte.nouvelle)}
                    onEnregistrer={(r) => {
                        setRegles((avant) => [...avant, r]);
                        setOuverte(null);
                    }}
                    onFermer={() => setOuverte(null)}
                />
            )}
            {ajout && (
                <ModaleAjout
                    env={env}
                    endroitInitial={ajout.endroit}
                    motifInitial={ajout.motif}
                    reglesExistantes={regles}
                    onAjouter={(r) => {
                        setRegles((avant) => [...avant, r]);
                        setAjout(null);
                    }}
                    onFermer={() => setAjout(null)}
                />
            )}
        </Theme>
    );
};
