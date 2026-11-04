"use client";

/**
 * [.mark] K6 : les onglets « Builder IA », « Appelant simulé » et « Juge » des Réglages du Labo, à la forme de la maquette
 * (`trois-cerveaux.tsx` : en tête la source actuelle avec son lien vers « Sources », puis deux colonnes de cartes). Tout vient de
 * routes réelles : le cerveau du builder (modèle, clé jamais relue, plafonds), ses préférences, ses options de construction
 * (M), ses sous-agents (C2, routes `/builder/sous-agents/reglages`) et la liste de ses outils (le registre d'actions). L'appelant et
 * le juge lisent leurs réglages existants et ouvrent la fenêtre de réglage qu'ils avaient déjà.
 * Chaque champ s'enregistre en le quittant, avec sa notification : il n'y a jamais de saisie en attente à perdre.
 */
import { BookOpen, Bot, DoorOpen, Gavel, Laptop, ListChecks, Monitor, Network, PhoneCall, Terminal, Wrench } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
    ecrireLesPreferencesApiV1BuilderPreferencesPut,
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet,
    lireLeCerveauApiV1BuilderCerveauGet,
    lireLesOptionsApiV1BuilderOptionsGet,
    lireLesPreferencesApiV1BuilderPreferencesGet,
    lireLesReglagesDesSousAgentsApiV1BuilderSousAgentsReglagesGet,
    listerLesActionsApiV1BuilderActionsGet,
    reglerLeCerveauApiV1BuilderCerveauPut,
    reglerLesOptionsApiV1BuilderOptionsPut,
    reglerLesSousAgentsApiV1BuilderSousAgentsReglagesPut,
} from "@/client";
import type { ReglagesAppelantSimule, ReglagesSousAgents, VueAction, VueCerveauLu, VueOptions, VueReglagesCerveau } from "@/client/types.gen";
import { OptionsDeConstruction } from "@/components/builder/ecran/OptionsDeConstruction";
import { ModaleReglagesAppelantSimule } from "@/components/mark/appelant-simule/ModaleReglagesAppelantSimule";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { useSources } from "@/components/mark/sources/useSources";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { cerveauxPartages, optionsPartagees } from "./lectures-partagees";

const T = {
    source: { en: "Source:", fr: "Source :" },
    sources: { en: "Sources", fr: "Sources" },
    claudeCode: { en: "Claude Code", fr: "Claude Code" },
    cleApi: { en: "API key", fr: "Clé d'API" },
    builderRole: { en: "Builds, fixes and tests the agents. Never publishes.", fr: "Construit, corrige et teste les agents. Ne publie jamais." },
    appelantRole: { en: "Plays the customer in the tests and the series. Never sees the criteria.", fr: "Joue le client dans les tests et les séries. Ne voit jamais les critères." },
    jugeRole: { en: "Rates what the code cannot check. Never decides a failure alone.", fr: "Note ce que le code ne sait pas vérifier. Ne décide jamais seul d'un échec." },
    modeleEtCle: { en: "Model and key", fr: "Modèle et clé" },
    modeleRegle: { en: "Rule: never the same model as the judge.", fr: "Règle : jamais le même modèle que le juge." },
    format: { en: "Provider format", fr: "Format du fournisseur" },
    anthropic: { en: "Anthropic (Claude)", fr: "Anthropic (Claude)" },
    openai: { en: "OpenAI-compatible (OpenAI, Mistral, Gemini...)", fr: "Compatible OpenAI (OpenAI, Mistral, Gemini...)" },
    modele: { en: "Model", fr: "Modèle" },
    adresse: { en: "Address (https, optional)", fr: "Adresse (https, facultative)" },
    adresseInfo: { en: "Empty: the provider's usual address.", fr: "Vide : l'adresse habituelle du fournisseur." },
    cle: { en: "Key", fr: "Clé" },
    clePosee: { en: "A key is saved. Leave empty to keep it.", fr: "Une clé est enregistrée. Laissez vide pour la garder." },
    cleAbsente: { en: "No key saved yet.", fr: "Aucune clé enregistrée." },
    cleInfo: { en: "Written, never read back: the key is kept encrypted.", fr: "Écrite, jamais relue : la clé est gardée chiffrée." },
    prompt: { en: "System prompt", fr: "Prompt système" },
    promptInfo: {
        en: "Lives in the library: versioned, editable on screen, proved by a bench before it becomes a Recipe.",
        fr: "Vit dans la bibliothèque : versionné, modifiable à l'écran, prouvé par un banc avant de devenir Recette.",
    },
    ouvrirBibliotheque: { en: "Open in the library", fr: "Ouvrir dans la bibliothèque" },
    plafonds: { en: "Ceilings", fr: "Plafonds" },
    plafondDepense: { en: "Spending per conversation ($, 0 = none)", fr: "Dépense par conversation ($, 0 = aucun)" },
    plafondJetons: { en: "Tokens per conversation", fr: "Jetons par conversation" },
    preferences: { en: "My preferences (how I like to work)", fr: "Mes préférences (ma façon de travailler)" },
    outils: { en: "Its tools", fr: "Ses outils" },
    outilsInfo: {
        en: "The same registry of actions serves both doors: the screen (function calls) and Claude Code (the fork's MCP server).",
        fr: "Le même registre d'actions sert aux deux portes : l'écran (appels de fonction) et Claude Code (serveur MCP du fork).",
    },
    aucun: { en: "None", fr: "Aucun" },
    sousAgents: { en: "Sub-agents", fr: "Sous-agents" },
    sousAgentsInfo: {
        en: "With sub-agents, the builder splits a long task and hands each part to a copy of itself. Each has its own conversation, only reads and tests, never changes the agent, then returns a summary. Several work at once, the next ones wait their turn. Without: the builder does everything itself, one task after the other.",
        fr: "Avec sous-agents : le builder découpe une tâche longue et confie chaque morceau à une copie de lui-même. Chaque sous-agent a sa propre conversation, ne fait que lire et tester, ne modifie jamais l'agent, puis rend un résumé. Plusieurs travaillent en même temps, les suivants attendent leur tour. Sans : le builder fait tout lui-même, une tâche après l'autre.",
    },
    modeleSous: { en: "Sub-agents' model", fr: "Modèle des sous-agents" },
    modeleSousInfo: { en: "Same key as the builder.", fr: "Même clé que le builder." },
    enMemeTemps: { en: "At most at the same time", fr: "En même temps, au plus" },
    enMemeTempsInfo: { en: "The next ones wait in line and leave as soon as one is done.", fr: "Les suivants attendent en file et partent dès qu'un sous-agent a fini." },
    parDelegation: { en: "Per delegation ($, 0 = none)", fr: "Par délégation ($, 0 = aucun)" },
    parDelegationInfo: {
        en: "Spending ceiling of the whole group; it also counts in the conversation's ceiling.",
        fr: "Plafond de dépense de tout le groupe ; il compte aussi dans le plafond de la conversation.",
    },
    analyser: { en: "Analyze the real calls", fr: "Analyser les vrais appels" },
    tester: { en: "Test in parallel", fr: "Tester en parallèle" },
    attaquer: { en: "Attack in parallel", fr: "Attaquer en parallèle" },
    comparer: { en: "Compare", fr: "Comparer" },
    controler: { en: "Check before publishing", fr: "Contrôler avant de publier" },
    ok: { en: "Settings saved.", fr: "Réglages enregistrés." },
    echec: { en: "The settings could not be saved.", fr: "Les réglages n'ont pas pu être enregistrés." },
    encours: { en: "Saving...", fr: "Enregistrement..." },
    regler: { en: "Settings...", fr: "Régler..." },
    modeleActuel: { en: "Model", fr: "Modèle" },
    sourceDeLaBrique: { en: "Source", fr: "Source" },
    serie: { en: "Series", fr: "Séries" },
    simultanes: { en: "Calls at once", fr: "Appels simultanés" },
    tailleSerie: { en: "Calls per series at most", fr: "Appels par série au plus" },
    plafondSerie: { en: "Spending cap of a series", fr: "Plafond de dépense d'une série" },
    appelant: { en: "Simulated caller", fr: "Appelant simulé" },
    juge: { en: "Judge", fr: "Juge" },
    consigne: { en: "Prompt", fr: "Consigne" },
    consigneInfo: {
        en: "The caller's and the judge's prompts are set in the settings window; the caller's personas live in the library.",
        fr: "Les consignes de l'appelant et du juge se règlent dans la fenêtre de réglage ; les personnages de l'appelant vivent dans la bibliothèque.",
    },
    personnages: { en: "Open the personas", fr: "Ouvrir les personnages" },
    interrupteur: { en: "Builder on", fr: "Builder allumé" },
    interrupteurInfo: {
        en: "Off: the builder does nothing, neither in the screen nor in Claude Code. Nothing already written is touched.",
        fr: "Éteint : le builder ne fait plus rien, ni dans l'écran ni dans Claude Code. Rien de ce qui est déjà écrit n'est touché.",
    },
    parMois: { en: "Per month, whole Lab ($, 0 = none)", fr: "Par mois, tout le Labo ($, 0 = aucun)" },
    parMoisInfo: {
        en: "Once reached, no new work starts (a running conversation stays bound by its own ceiling). Counts every conversation moved this month (UTC), the sub-agents included.",
        fr: "Une fois atteint, aucun nouveau travail ne démarre (une conversation en cours reste bornée par son propre plafond). Compte toute conversation bougée ce mois-ci (UTC), sous-agents compris.",
    },
    depenseDuMois: { en: "Spent this month:", fr: "Dépensé ce mois-ci :" },
    secours: { en: "Not in the library: the code's text is used.", fr: "Absent de la bibliothèque : le texte du code sert." },
    statutRecette: { en: "Proven", fr: "Recette" },
    statutRejete: { en: "Rejected", fr: "Rejeté" },
    statutCandidat: { en: "Candidate", fr: "Candidat" },
    recoit: { en: "What it receives", fr: "Ce qu'il reçoit" },
    recoitInfo: { en: "Injected by the code, every time.", fr: "Injecté par le code, à chaque fois." },
    vide: { en: "empty", fr: "vide" },
    absent: { en: "missing", fr: "absent" },
    portes: { en: "Doors", fr: "Portes" },
    porteEcran: { en: "In the screen", fr: "Dans l'écran" },
    porteEcranInfo: {
        en: "The brain above, paid per use by its API key, capped. Off: the chat of the screen does not open.",
        fr: "Le cerveau ci-dessus, payé à l'usage par sa clé d'API, plafonné. Éteinte : le chat de l'écran ne s'ouvre plus.",
    },
    porteClaudeCode: { en: "In Claude Code (MCP)", fr: "Dans Claude Code (MCP)" },
    porteClaudeCodeInfo: {
        en: "Everyone's subscription: Claude reads the method, the conventions and the recipes through the MCP and calls the same actions. What it changes arrives here as a draft, to validate in the screen. Off: the MCP refuses every action.",
        fr: "Abonnement de chacun : Claude lit la méthode, les conventions et les recettes par le MCP, et appelle les mêmes actions. Ce qu'il change arrive ici en brouillon, à valider dans l'écran. Éteinte : le MCP refuse toute action.",
    },
    actions: { en: "actions", fr: "actions" },
    limitesJuge: { en: "Limits", fr: "Limites" },
    passes: { en: "Passes when it is close", fr: "Passes quand c'est serré" },
    passesInfo: { en: "Up to this many passes when an answer lacks confidence; majority vote.", fr: "Jusqu'à ce nombre de passes quand une réponse manque de confiance ; vote à la majorité." },
    calibrage: { en: "Calibration", fr: "Calibrage" },
    calibrageInfo: { en: "The judge's opinion is marked uncalibrated until it agrees with our notes at this rate, on at least the minimum number of notes.", fr: "L'avis du juge reste marqué non calibré tant qu'il n'est pas d'accord avec nos notes à ce taux, sur au moins le nombre de notes minimal." },
    d_accord: { en: "agreement", fr: "d'accord" },
    sur: { en: "notes at least", fr: "notes au moins" },
    aucunOutil: { en: "None", fr: "Aucun" },
    aucunOutilInfo: {
        en: "It only talks (caller) or rates (judge). It runs on our server, whichever door launched the tests.",
        fr: "Il ne fait que parler (appelant) ou noter (juge). Il tourne sur notre serveur, quelle que soit la porte utilisée pour lancer les tests.",
    },
    ses_outils: { en: "Its tools", fr: "Ses outils" },
    recu_methode: { en: "The builder's method (library)", fr: "La méthode du builder (bibliothèque)" },
    recu_conventions: { en: ".mark conventions (library)", fr: "Les conventions .mark (bibliothèque)" },
    recu_recette_de_l_agent: { en: "The recipe set on the agent", fr: "La recette indiquée sur l'agent" },
    recu_preferences: { en: "Your preferences", fr: "Vos préférences" },
    recu_etat_de_l_agent: { en: "The agent's state, read again from disk: sheet, design, pending changes, latest tests", fr: "L'état de l'agent relu sur le disque : fiche, conception, changements, derniers tests" },
    recu_recettes_a_la_demande: { en: "The library's recipes, on demand", fr: "Les recettes de la bibliothèque, à la demande" },
    recu_personnage: { en: "The test's persona", fr: "Le personnage du test" },
    recu_comportements: { en: "Its behaviours (corrects itself, gives little by little...)", fr: "Ses comportements (se corrige, donne au compte-gouttes...)" },
    recu_scenario: { en: "The scenario: what it wants, what it knows", fr: "Le scénario : ce qu'il veut, ce qu'il sait" },
    recu_repliques: { en: "The agent's lines, turn by turn", fr: "Les répliques de l'agent, tour par tour" },
    recu_transcription: { en: "The conversation's transcript", fr: "La transcription de la conversation" },
    recu_criteres: { en: "The test's criteria, or the grid for a real call", fr: "Les critères du test, ou la grille pour un vrai appel" },
    recu_verdict_du_code: { en: "The verdict already set by the code (tools, steps, sheet)", fr: "Le verdict déjà posé par le code (outils, étapes, fiche)" },
} satisfies Record<string, Texte>;

const USAGES = ["analyser", "tester", "attaquer", "comparer", "controler"] as const;

type Reponse = { error?: unknown };

const Carte = ({ children }: { children: ReactNode }) => <div className="space-y-3 rounded-xl border bg-card p-5">{children}</div>;
const Ligne = ({ libelle, info, children }: { libelle: string; info?: string; children: ReactNode }) => (
    <div className="flex items-center gap-3 text-sm">
        <span className="flex flex-1 items-center gap-1.5 text-muted-foreground">
            {libelle}
            {info && <Info>{info}</Info>}
        </span>
        {children}
    </div>
);

/** En tête de chaque onglet : la source actuelle des briques et le lien vers « Sources » (maquette `SourceActuelle`). */
export function SourceActuelle({ briques, aller }: { briques: ("builder" | "appelant" | "juge_tests" | "juge_appels")[]; aller: () => void }) {
    const { t } = useLangue();
    const { sources } = useSources();
    if (!sources) return null;
    const dit = [...new Set(briques.map((b) => (sources[b] === "claude_code" ? t(T.claudeCode) : t(T.cleApi))))].join(", ");
    return (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Terminal className="size-4 text-(--acc)" aria-hidden />
            {t(T.source)} {dit}
            <button type="button" onClick={aller} className="cursor-pointer text-(--acc) hover:font-semibold">
                {t(T.sources)}
            </button>
        </p>
    );
}

/** Un champ qui s'enregistre en le quittant, seulement s'il a changé. */
function ChampSimple({
    id,
    libelle,
    valeur,
    onEnregistrer,
    ...reste
}: {
    id: string;
    libelle: string;
    valeur: string;
    onEnregistrer: (v: string) => void;
    type?: string;
    inputMode?: "decimal" | "numeric";
    className?: string;
    placeholder?: string;
}) {
    const [saisie, setSaisie] = useState(valeur);
    useEffect(() => setSaisie(valeur), [valeur]);
    return (
        <Input
            id={id}
            aria-label={libelle}
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onBlur={() => saisie !== valeur && onEnregistrer(saisie)}
            autoComplete="off"
            {...reste}
        />
    );
}

/** Le prompt système tel que la bibliothèque le tient : nom, version, statut (ou le secours du code). */
function CartePrompt({ lu }: { lu: VueCerveauLu | null }) {
    const { t } = useLangue();
    const p = lu?.prompt;
    return (
        <Carte>
            <p className="flex items-center gap-2 text-sm font-medium">
                <BookOpen className="size-4 text-muted-foreground" aria-hidden />
                {t(T.prompt)}
                <Info>{t(T.promptInfo)}</Info>
            </p>
            {p && (
                <div className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm" data-prompt={p.slug}>
                    <span className="flex-1">{p.titre ?? p.libelle_famille}</span>
                    {p.version !== null && p.version !== undefined ? (
                        <span className="text-xs text-muted-foreground">
                            v{p.version} · {p.statut === "recette" ? t(T.statutRecette) : p.statut === "rejete" ? t(T.statutRejete) : t(T.statutCandidat)}
                        </span>
                    ) : (
                        <span className="text-xs text-muted-foreground">{t(T.secours)}</span>
                    )}
                </div>
            )}
            <Button variant="outline" size="sm" asChild>
                <Link href="/labo/bibliotheque">{t(T.ouvrirBibliotheque)}</Link>
            </Button>
        </Carte>
    );
}

/** « Ce qu'il reçoit » : les blocs que le code injecte, avec « vide » ou « absent » quand la donnée n'existe pas. */
function CarteRecoit({ lu }: { lu: VueCerveauLu | null }) {
    const { t } = useLangue();
    if (!lu) return null;
    return (
        <Carte>
            <p className="flex items-center gap-1.5 text-sm font-medium">
                <ListChecks className="size-4 text-muted-foreground" aria-hidden />
                {t(T.recoit)}
                <Info>{t(T.recoitInfo)}</Info>
            </p>
            <ul className="list-disc space-y-1.5 pl-5 text-sm" data-liste="ce-quil-recoit">
                {lu.recoit.map((r) => {
                    const cle = `recu_${r.cle}` as keyof typeof T;
                    return (
                        <li key={r.cle}>
                            {t(T[cle])}
                            {r.present === false && <span className="text-muted-foreground"> ({r.cle === "preferences" ? t(T.vide) : t(T.absent)})</span>}
                        </li>
                    );
                })}
            </ul>
        </Carte>
    );
}

/** Une écriture des options : relit l'état du serveur d'abord, change SEUL le champ voulu (les autres réglages d'options ne sont jamais écrasés). */
async function ecrireUneOption(morceau: Partial<VueOptions>): Promise<VueOptions | null> {
    const frais = await lireLesOptionsApiV1BuilderOptionsGet();
    if (frais.error || !frais.data) return null;
    const r = await reglerLesOptionsApiV1BuilderOptionsPut({ body: { ...frais.data, ...morceau } });
    return r.error || !r.data ? null : r.data;
}

export function OngletBuilderIA({ aller }: { aller: () => void }) {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [cerveau, setCerveau] = useState<VueReglagesCerveau | null>(null);
    const [preferences, setPreferences] = useState("");
    const [sous, setSous] = useState<ReglagesSousAgents | null>(null);
    const [actions, setActions] = useState<VueAction[] | null>(null);
    const prete = !loading && Boolean(user);
    const { valeur: vue } = cerveauxPartages.useLecture(prete);
    const { valeur: opts, poser: poserOpts } = optionsPartagees.useLecture(prete);
    const [erreurLecture, setErreurLecture] = useState(false);
    const [erreurChamp, setErreurChamp] = useState<string | null>(null);

    const lire = useCallback(async () => {
        const [c, p, s, a] = await Promise.all([
            lireLeCerveauApiV1BuilderCerveauGet(),
            lireLesPreferencesApiV1BuilderPreferencesGet(),
            lireLesReglagesDesSousAgentsApiV1BuilderSousAgentsReglagesGet(),
            listerLesActionsApiV1BuilderActionsGet(),
        ]);
        if (c.error || !c.data) return setErreurLecture(true);
        setErreurLecture(false);
        setCerveau(c.data);
        setPreferences(p.data?.texte ?? "");
        setSous(s.data ?? {});
        setActions(a.data ?? []);
    }, []);
    useEffect(() => {
        if (!loading && user) void lire();
    }, [loading, user, lire]);

    if (erreurLecture) return <EtatVide cas="erreur" reessayer={() => void lire()} />;
    if (!cerveau || !sous) return <EtatVide cas="chargement" lignes={5} />;

    // Le client d'API ne lève pas sur une erreur HTTP : `echecSi` la traite comme un échec ; jamais le texte brut du serveur à l'écran.
    const suivre = (appel: Promise<Reponse>, quandBon?: () => void) =>
        notifier.suivre(
            appel.then((r) => {
                if (!r.error) quandBon?.();
                else setErreurChamp(detailFromError(r.error, t(T.echec)));
                return r;
            }),
            { encours: T.encours, succes: T.ok, echec: T.echec, echecSi: (r) => r.error },
        );
    const enregistrerCerveau = (morceau: Record<string, unknown>) => {
        setErreurChamp(null);
        suivre(reglerLeCerveauApiV1BuilderCerveauPut({ body: { ...cerveau, ...morceau } as never }), undefined);
        // la vue relit ce que le serveur a gardé (la clé n'est jamais relue)
        void lireLeCerveauApiV1BuilderCerveauGet().then((r) => r.data && setCerveau(r.data));
        void cerveauxPartages.relire();
    };
    // L'interrupteur du builder et ses deux portes : une option à la fois, avec sa notification.
    const regler = (morceau: Partial<VueOptions>) =>
        notifier.suivre(
            ecrireUneOption(morceau).then((nouvelles) => {
                if (nouvelles) {
                    poserOpts(nouvelles);
                    void cerveauxPartages.relire();
                }
                return { error: nouvelles ? undefined : true };
            }),
            { encours: T.encours, succes: T.ok, echec: T.echec, echecSi: (r) => r.error },
        );
    const enregistrerSous = (morceau: Partial<ReglagesSousAgents>) => {
        const suivant = { ...sous, ...morceau };
        setSous(suivant);
        suivre(reglerLesSousAgentsApiV1BuilderSousAgentsReglagesPut({ body: suivant }));
    };
    const usages = new Set(sous.usages ?? USAGES);
    const actifs = sous.actif ?? true;

    return (
        <div className="space-y-4">
            <SourceActuelle briques={["builder"]} aller={aller} />
            <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-4">
                    <Carte>
                        <div className="flex items-center gap-2">
                            <Bot className="size-5 text-(--acc)" aria-hidden />
                            <p className="font-medium">{t({ en: "Builder AI", fr: "Builder IA" })}</p>
                            <Info>{`${t(T.builderRole)} ${t(T.interrupteurInfo)}`}</Info>
                            <Switch
                                className="ml-auto"
                                aria-label={t(T.interrupteur)}
                                checked={opts ? !opts.builder_coupe : true}
                                disabled={!opts}
                                onCheckedChange={(v) => regler({ builder_coupe: !v })}
                            />
                        </div>

                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t(T.modeleEtCle)}
                            <Info>{t(T.modeleRegle)}</Info>
                        </p>
                        <div className="space-y-2">
                            <Ligne libelle={t(T.format)}>
                                <ListeDeroulante
                                    aria-label={t(T.format)}
                                    className="h-8 w-56 cursor-pointer rounded-md border bg-background px-2 text-sm"
                                    value={cerveau.format ?? "anthropic"}
                                    onChange={(e) => enregistrerCerveau({ format: e.target.value })}
                                >
                                    <option value="anthropic">{t(T.anthropic)}</option>
                                    <option value="openai">{t(T.openai)}</option>
                                </ListeDeroulante>
                            </Ligne>
                            <Ligne libelle={t(T.modele)}>
                                <ChampSimple id="cerveau-modele" libelle={t(T.modele)} valeur={cerveau.modele ?? ""} className="h-8 w-56" onEnregistrer={(v) => v.trim() && enregistrerCerveau({ modele: v.trim() })} />
                            </Ligne>
                            <Ligne libelle={t(T.adresse)} info={t(T.adresseInfo)}>
                                <ChampSimple id="cerveau-adresse" libelle={t(T.adresse)} valeur={cerveau.adresse ?? ""} className="h-8 w-56" onEnregistrer={(v) => enregistrerCerveau({ adresse: v.trim() })} />
                            </Ligne>
                            <Ligne libelle={t(T.cle)} info={t(T.cleInfo)}>
                                <ChampSimple
                                    id="cerveau-cle"
                                    libelle={t(T.cle)}
                                    type="password"
                                    valeur=""
                                    placeholder={cerveau.cle_posee ? "••••••••" : ""}
                                    className="h-8 w-56"
                                    onEnregistrer={(v) => v.trim() && enregistrerCerveau({ cle: v.trim() })}
                                />
                            </Ligne>
                            <p className="text-right text-xs text-muted-foreground" data-cle-posee={cerveau.cle_posee ? "oui" : "non"}>
                                {cerveau.cle_posee ? t(T.clePosee) : t(T.cleAbsente)}
                            </p>
                            {erreurChamp && (
                                <p role="alert" className="text-sm text-destructive">
                                    {erreurChamp}
                                </p>
                            )}
                        </div>
                    </Carte>
                    <CartePrompt lu={vue?.builder ?? null} />
                    <Carte>
                        <p className="text-sm font-medium">{t(T.plafonds)}</p>
                        <Ligne libelle={t(T.plafondDepense)}>
                            <ChampSimple id="cerveau-plafond-depense" libelle={t(T.plafondDepense)} inputMode="decimal" valeur={String(cerveau.plafond_depense ?? 2)} className="h-8 w-44" onEnregistrer={(v) => enregistrerCerveau({ plafond_depense: Number(v) || 0 })} />
                        </Ligne>
                        <Ligne libelle={t(T.plafondJetons)}>
                            <ChampSimple id="cerveau-plafond-jetons" libelle={t(T.plafondJetons)} inputMode="numeric" valeur={String(cerveau.plafond_jetons ?? 1_500_000)} className="h-8 w-44" onEnregistrer={(v) => enregistrerCerveau({ plafond_jetons: Number(v) || 1_500_000 })} />
                        </Ligne>
                        <Ligne libelle={t(T.parMois)} info={t(T.parMoisInfo)}>
                            <ChampSimple id="cerveau-plafond-mois" libelle={t(T.parMois)} inputMode="decimal" valeur={String(cerveau.plafond_mois ?? 0)} className="h-8 w-44" onEnregistrer={(v) => enregistrerCerveau({ plafond_mois: Math.max(0, Number(v) || 0) })} />
                        </Ligne>
                        {vue && (
                            <p className="text-right text-xs text-muted-foreground" data-depense-du-mois={vue.depense_du_mois}>
                                {t(T.depenseDuMois)} {vue.depense_du_mois.toFixed(2)} $
                            </p>
                        )}
                        <div className="space-y-1.5 border-t pt-3">
                            <label htmlFor="cerveau-preferences" className="text-sm text-muted-foreground">
                                {t(T.preferences)}
                            </label>
                            <Textarea
                                id="cerveau-preferences"
                                className="min-h-20"
                                value={preferences}
                                onChange={(e) => setPreferences(e.target.value)}
                                onBlur={() => suivre(ecrireLesPreferencesApiV1BuilderPreferencesPut({ body: { texte: preferences } }))}
                            />
                        </div>
                    </Carte>
                </div>
                <div className="space-y-4">
                    <CarteRecoit lu={vue?.builder ?? null} />
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <Wrench className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.outils)}
                            <Info>{t(T.outilsInfo)}</Info>
                        </p>
                        {actions === null || actions.length === 0 ? (
                            <p className="text-sm text-muted-foreground">{t(T.aucun)}</p>
                        ) : (
                            <ul className="max-h-72 list-disc space-y-1 overflow-y-auto pl-5 text-sm" data-liste="outils-du-builder">
                                {actions
                                    .filter((a) => a.disponible)
                                    .map((a) => (
                                        <li key={a.nom} title={a.description}>
                                            {a.nom}
                                        </li>
                                    ))}
                            </ul>
                        )}
                    </Carte>
                    <Carte>
                        <div className="flex items-center gap-2">
                            <Network className="size-4 text-muted-foreground" aria-hidden />
                            <p className="flex flex-1 items-center gap-1.5 text-sm font-medium">
                                {t(T.sousAgents)}
                                <Info>{t(T.sousAgentsInfo)}</Info>
                            </p>
                            <Switch aria-label={t(T.sousAgents)} checked={actifs} onCheckedChange={(v) => enregistrerSous({ actif: v })} />
                        </div>
                        {actifs && (
                            <>
                                <div className="space-y-2">
                                    {USAGES.map((u) => (
                                        <div key={u} className="flex items-center gap-3 text-sm">
                                            <span className="flex-1">{t(T[u])}</span>
                                            <Switch
                                                aria-label={t(T[u])}
                                                checked={usages.has(u)}
                                                onCheckedChange={(v) => enregistrerSous({ usages: USAGES.filter((x) => (x === u ? v : usages.has(x))) })}
                                            />
                                        </div>
                                    ))}
                                </div>
                                <div className="space-y-2 border-t pt-3">
                                    <Ligne libelle={t(T.modeleSous)} info={t(T.modeleSousInfo)}>
                                        <ChampSimple id="sous-modele" libelle={t(T.modeleSous)} valeur={sous.modele ?? ""} className="h-8 w-44" onEnregistrer={(v) => v.trim() && enregistrerSous({ modele: v.trim() })} />
                                    </Ligne>
                                    <Ligne libelle={t(T.enMemeTemps)} info={t(T.enMemeTempsInfo)}>
                                        <ChampSimple id="sous-simultanes" libelle={t(T.enMemeTemps)} inputMode="numeric" valeur={String(sous.en_meme_temps ?? 3)} className="h-8 w-44" onEnregistrer={(v) => enregistrerSous({ en_meme_temps: Math.min(10, Math.max(1, Number(v) || 3)) })} />
                                    </Ligne>
                                    <Ligne libelle={t(T.parDelegation)} info={t(T.parDelegationInfo)}>
                                        <ChampSimple id="sous-plafond" libelle={t(T.parDelegation)} inputMode="decimal" valeur={String(sous.plafond_delegation ?? 1)} className="h-8 w-44" onEnregistrer={(v) => enregistrerSous({ plafond_delegation: Math.max(0, Number(v) || 0) })} />
                                    </Ligne>
                                </div>
                            </>
                        )}
                    </Carte>
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <DoorOpen className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.portes)}
                        </p>
                        <div className="flex items-center gap-3 text-sm">
                            <Monitor className="size-4 text-muted-foreground" aria-hidden />
                            <span className="flex-1">
                                {t(T.porteEcran)}
                                {vue && <span className="text-xs text-muted-foreground"> · {vue.portes.ecran.actions} {t(T.actions)}</span>}
                            </span>
                            <Info>{t(T.porteEcranInfo)}</Info>
                            <Switch aria-label={t(T.porteEcran)} checked={opts ? !opts.porte_ecran_coupee : true} disabled={!opts} onCheckedChange={(v) => regler({ porte_ecran_coupee: !v })} />
                        </div>
                        <div className="flex items-center gap-3 text-sm">
                            <Laptop className="size-4 text-muted-foreground" aria-hidden />
                            <span className="flex-1">
                                {t(T.porteClaudeCode)}
                                {vue && <span className="text-xs text-muted-foreground"> · {vue.portes.claude_code.actions} {t(T.actions)}</span>}
                            </span>
                            <Info>{t(T.porteClaudeCodeInfo)}</Info>
                            <Switch aria-label={t(T.porteClaudeCode)} checked={opts ? !opts.porte_claude_code_coupee : true} disabled={!opts} onCheckedChange={(v) => regler({ porte_claude_code_coupee: !v })} />
                        </div>
                    </Carte>
                    <Carte>
                        <OptionsDeConstruction />
                    </Carte>
                </div>
            </div>
        </div>
    );
}

/** L'appelant simulé et le juge : leurs réglages existants, lus ici et réglés dans la fenêtre qu'ils avaient déjà. */
export function OngletAppelantOuJuge({ role, aller }: { role: "appelant" | "juge"; aller: () => void }) {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [reglages, setReglages] = useState<ReglagesAppelantSimule | null>(null);
    const [erreur, setErreur] = useState(false);
    const [fenetre, setFenetre] = useState(false);
    const { valeur: vue } = cerveauxPartages.useLecture(!loading && Boolean(user));
    const lire = useCallback(async () => {
        const r = await getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet();
        if (r.error || !r.data) return setErreur(true);
        setErreur(false);
        setReglages(r.data);
    }, []);
    useEffect(() => {
        if (!loading && user) void lire();
    }, [loading, user, lire]);

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void lire()} />;
    if (!reglages) return <EtatVide cas="chargement" lignes={4} />;

    const appelant = role === "appelant";
    const Icone = appelant ? PhoneCall : Gavel;
    const lu = appelant ? reglages.appelant : reglages.juge;
    return (
        <div className="space-y-4">
            <SourceActuelle briques={appelant ? ["appelant"] : ["juge_tests", "juge_appels"]} aller={aller} />
            <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-4">
                    <Carte>
                        <div className="flex items-center gap-2">
                            <Icone className="size-5 text-(--acc)" aria-hidden />
                            <p className="font-medium">{appelant ? t(T.appelant) : t(T.juge)}</p>
                            <Info>{appelant ? t(T.appelantRole) : t(T.jugeRole)}</Info>
                        </div>
                        <Ligne libelle={t(T.modeleActuel)}>
                            <span className="text-sm">{lu?.modele ?? ""}</span>
                        </Ligne>
                        <Ligne libelle={t(T.sourceDeLaBrique)}>
                            <span className="text-sm">{lu?.source === "claude_code" ? t(T.claudeCode) : t(T.cleApi)}</span>
                        </Ligne>
                        <Button variant="outline" size="sm" onClick={() => setFenetre(true)}>
                            {t(T.regler)}
                        </Button>
                    </Carte>
                    <CartePrompt lu={appelant ? (vue?.appelant ?? null) : (vue?.juge ?? null)} />
                    {appelant && (
                        <Carte>
                            <p className="text-sm font-medium">{t(T.serie)}</p>
                            <Ligne libelle={t(T.simultanes)}>
                                <span className="text-sm">{reglages.simultanes ?? 1}</span>
                            </Ligne>
                            <Ligne libelle={t(T.tailleSerie)}>
                                <span className="text-sm">{reglages.taille_max_serie ?? 10}</span>
                            </Ligne>
                            <Ligne libelle={t(T.plafondSerie)}>
                                <span className="text-sm">{reglages.plafond ?? 5}</span>
                            </Ligne>
                        </Carte>
                    )}
                    {!appelant && vue && (
                        <Carte>
                            <p className="text-sm font-medium">{t(T.limitesJuge)}</p>
                            <Ligne libelle={t(T.passes)} info={t(T.passesInfo)}>
                                <span className="text-sm">{vue.limites_du_juge.passes_max}</span>
                            </Ligne>
                            <Ligne libelle={t(T.calibrage)} info={t(T.calibrageInfo)}>
                                <span className="text-sm">
                                    {Math.round(vue.limites_du_juge.accord_min * 100)} % {t(T.d_accord)} · {vue.limites_du_juge.notes_min} {t(T.sur)}
                                </span>
                            </Ligne>
                        </Carte>
                    )}
                </div>
                <div className="space-y-4">
                    <CarteRecoit lu={appelant ? (vue?.appelant ?? null) : (vue?.juge ?? null)} />
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <Wrench className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.ses_outils)}
                        </p>
                        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                            {t(T.aucunOutil)}
                            <Info>{t(T.aucunOutilInfo)}</Info>
                        </p>
                    </Carte>
                </div>
            </div>
            <ModaleReglagesAppelantSimule
                ouverte={fenetre}
                onFermer={() => {
                    setFenetre(false);
                    void lire();
                }}
            />
        </div>
    );
}
