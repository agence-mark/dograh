"use client";

/**
 * [.mark] K6 : les onglets « Builder IA », « Appelant simulé » et « Juge » des Réglages du Labo, à la forme de la maquette
 * (`trois-cerveaux.tsx` : en tête la source actuelle avec son lien vers « Sources », puis deux colonnes de cartes). Tout vient de
 * routes réelles : le cerveau du builder (modèle, clé jamais relue, plafonds), ses préférences, ses options de construction
 * (M), ses sous-agents (C2, routes `/builder/sous-agents/reglages`) et la liste de ses outils (le registre d'actions). L'appelant et
 * le juge lisent leurs réglages existants et ouvrent la fenêtre de réglage qu'ils avaient déjà.
 * Chaque champ s'enregistre en le quittant, avec sa notification : il n'y a jamais de saisie en attente à perdre.
 */
import { BookOpen, Bot, Gavel, Network, PhoneCall, Terminal, Wrench } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
    ecrireLesPreferencesApiV1BuilderPreferencesPut,
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet,
    lireLeCerveauApiV1BuilderCerveauGet,
    lireLesPreferencesApiV1BuilderPreferencesGet,
    lireLesReglagesDesSousAgentsApiV1BuilderSousAgentsReglagesGet,
    listerLesActionsApiV1BuilderActionsGet,
    reglerLeCerveauApiV1BuilderCerveauPut,
    reglerLesSousAgentsApiV1BuilderSousAgentsReglagesPut,
} from "@/client";
import type { ReglagesAppelantSimule, ReglagesSousAgents, VueAction, VueReglagesCerveau } from "@/client/types.gen";
import { OptionsDeConstruction } from "@/components/builder/ecran/OptionsDeConstruction";
import { ModaleReglagesAppelantSimule } from "@/components/mark/appelant-simule/ModaleReglagesAppelantSimule";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { useSources } from "@/components/mark/sources/useSources";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

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

export function OngletBuilderIA({ aller }: { aller: () => void }) {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [cerveau, setCerveau] = useState<VueReglagesCerveau | null>(null);
    const [preferences, setPreferences] = useState("");
    const [sous, setSous] = useState<ReglagesSousAgents | null>(null);
    const [actions, setActions] = useState<VueAction[] | null>(null);
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
    };
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
                            <p className="font-medium">Builder IA</p>
                            <Info>{t(T.builderRole)}</Info>
                        </div>
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t(T.modeleEtCle)}
                            <Info>{t(T.modeleRegle)}</Info>
                        </p>
                        <div className="space-y-2">
                            <Ligne libelle={t(T.format)}>
                                <select
                                    aria-label={t(T.format)}
                                    className="h-8 w-56 cursor-pointer rounded-md border bg-background px-2 text-sm"
                                    value={cerveau.format ?? "anthropic"}
                                    onChange={(e) => enregistrerCerveau({ format: e.target.value })}
                                >
                                    <option value="anthropic">{t(T.anthropic)}</option>
                                    <option value="openai">{t(T.openai)}</option>
                                </select>
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
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <BookOpen className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.prompt)}
                            <Info>{t(T.promptInfo)}</Info>
                        </p>
                        <Button variant="outline" size="sm" asChild>
                            <Link href="/labo/bibliotheque">{t(T.ouvrirBibliotheque)}</Link>
                        </Button>
                    </Carte>
                    <Carte>
                        <p className="text-sm font-medium">{t(T.plafonds)}</p>
                        <Ligne libelle={t(T.plafondDepense)}>
                            <ChampSimple id="cerveau-plafond-depense" libelle={t(T.plafondDepense)} inputMode="decimal" valeur={String(cerveau.plafond_depense ?? 2)} className="h-8 w-44" onEnregistrer={(v) => enregistrerCerveau({ plafond_depense: Number(v) || 0 })} />
                        </Ligne>
                        <Ligne libelle={t(T.plafondJetons)}>
                            <ChampSimple id="cerveau-plafond-jetons" libelle={t(T.plafondJetons)} inputMode="numeric" valeur={String(cerveau.plafond_jetons ?? 1_500_000)} className="h-8 w-44" onEnregistrer={(v) => enregistrerCerveau({ plafond_jetons: Number(v) || 1_500_000 })} />
                        </Ligne>
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
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <Wrench className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.outils)}
                            <Info>{t(T.outilsInfo)}</Info>
                        </p>
                        {actions === null || actions.length === 0 ? (
                            <p className="text-sm text-muted-foreground">{t(T.aucun)}</p>
                        ) : (
                            <ul className="list-disc space-y-1 pl-5 text-sm" data-liste="outils-du-builder">
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
                    <Carte>
                        <p className="flex items-center gap-2 text-sm font-medium">
                            <BookOpen className="size-4 text-muted-foreground" aria-hidden />
                            {t(T.consigne)}
                            <Info>{t(T.consigneInfo)}</Info>
                        </p>
                        <Button variant="outline" size="sm" asChild>
                            <Link href="/labo/bibliotheque">{appelant ? t(T.personnages) : t(T.ouvrirBibliotheque)}</Link>
                        </Button>
                    </Carte>
                </div>
                {appelant && (
                    <div className="space-y-4">
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
                    </div>
                )}
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
