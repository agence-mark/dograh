"use client";

import { ArrowDown, ArrowLeftRight, ArrowUp, ChevronDown, Minus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { comparerEnDuelApiV1BuilderBranchesWorkflowIdComparerGet } from "@/client/sdk.gen";
import type { ComparaisonVue, LigneDeConfiguration, MesureDeComparaison } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { useAuth } from "@/lib/auth";

import { FenetreFusion } from "./FenetreFusion";
import { useBranches } from "./useBranches";

/**
 * [.mark] Partie 3, SA-L3c (05 § 18, maquette `comparer-branches.tsx`) : « Comparer en duel ». Deux branches ou deux versions face à
 * face sur la même période : deux cartes, un verdict d'une ligne, le tableau des résultats (meilleure valeur sur fond vert, colonne
 * « Écart » fléchée et colorée, petite barre), puis la différence de configuration en lignes avant / après, groupée par famille et
 * repliable. Les chiffres sont ceux de la page Qualité, en une lecture côté serveur.
 */
const T = {
    titre: { en: "Compare", fr: "Comparer" },
    info: {
        en: "Two branches or two versions, over the same period. The calls are split by branch: compare before merging.",
        fr: "Deux branches ou deux versions, sur la même période. Le trafic est réparti par branche : on compare avant de fusionner.",
    },
    periode: { en: "Last 7 days", fr: "7 derniers jours" },
    echanger: { en: "Swap the two sides", fr: "Échanger les deux côtés" },
    coteA: { en: "Side A", fr: "Côté A" },
    coteB: { en: "Side B", fr: "Côté B" },
    contre: { en: "against", fr: "contre" },
    resultats: { en: "Results", fr: "Résultats" },
    resultatsInfo: {
        en: "Over the calls each side received. The best value is on a green ground; the gap reads from A to B. A small sample is read with care.",
        fr: "Sur la part des appels que chaque côté a reçue. La meilleure valeur est sur fond vert ; l'écart se lit de A vers B. Un petit échantillon se lit avec prudence.",
    },
    mesure: { en: "Measure", fr: "Mesure" },
    ecart: { en: "Gap (A → B)", fr: "Écart (A → B)" },
    config: { en: "Configuration difference", fr: "Différence de configuration" },
    configInfo: {
        en: "Field by field: flow, prompts, settings. Red struck line: the value in A; green line: the value in B.",
        fr: "Champ par champ : graphe, prompts, réglages. Ligne rouge barrée : la valeur en A ; ligne verte : la valeur en B.",
    },
    aucuneDiff: { en: "No difference.", fr: "Aucune différence." },
    identiques: { en: "Choose two different sides.", fr: "Choisissez deux côtés différents." },
    absent: { en: "(absent)", fr: "(absent)" },
    erreur: { en: "The comparison could not be read. Try again.", fr: "La comparaison n'a pas pu être lue. Réessayez." },
    insuffisant: {
        en: "Fewer than 5 calls on a side: too early to say who does better.",
        fr: "Moins de 5 appels d'un côté : trop tôt pour dire lequel fait mieux.",
    },
    egalite: { en: "Neither side does clearly better.", fr: "Aucun côté ne fait clairement mieux." },
    traffic: { en: "of the calls", fr: "du trafic" },
    appels: { en: "calls", fr: "appels" },
} satisfies Record<string, Texte>;

const MESURES: Record<string, Texte> = {
    part: { en: "Share of the calls", fr: "Part du trafic" },
    appels: { en: "Calls", fr: "Appels" },
    resolution: { en: "Resolved", fr: "Résolus" },
    transferts: { en: "Transferred", fr: "Transférés" },
    note: { en: "Judge score", fr: "Note du juge" },
    cout: { en: "Cost per call", fr: "Coût par appel" },
    latence: { en: "Median latency", fr: "Latence médiane" },
};

const FAMILLES: Record<string, Texte> = {
    graphe: { en: "Flow", fr: "Graphe" },
    prompts: { en: "Prompts", fr: "Prompts" },
    reglages: { en: "Settings", fr: "Réglages" },
    phrases: { en: "Phrases", fr: "Phrases" },
    variables: { en: "Variables", fr: "Variables" },
};

const fr = (n: number, d = 2) => n.toLocaleString("fr-FR", { maximumFractionDigits: d });

/** Une valeur du serveur telle qu'on la lit : parts en %, note sur 5, coût en $, latence en s. */
export function formater(cle: string, v: number | null | undefined): string {
    if (v === null || v === undefined) return "–";
    if (cle === "part") return `${v} %`;
    if (cle === "appels") return String(v);
    if (cle === "resolution" || cle === "transferts") return `${fr(v * 100, 0)} %`;
    if (cle === "note") return `${fr(v, 1)} / 5`;
    if (cle === "cout") return `${fr(v, 3)} $`;
    return `${fr(v, 2)} s`;
}

/** L'écart A → B : le texte et le sens de la flèche (`null` : une des deux valeurs manque). */
export function ecartDe(m: MesureDeComparaison): { texte: string; signe: number } | null {
    if (m.ecart === null || m.ecart === undefined) return null;
    const d = m.ecart;
    const brut = m.cle === "resolution" || m.cle === "transferts" ? d * 100 : d;
    const unite = m.cle === "part" || m.cle === "resolution" || m.cle === "transferts" ? " pts" : m.cle === "cout" ? " $" : m.cle === "latence" ? " s" : "";
    return { texte: `${d > 0 ? "+" : d < 0 ? "−" : ""}${fr(Math.abs(brut), m.cle === "cout" ? 3 : 2)}${unite}`, signe: Math.sign(d) };
}

function PointBranche({ part }: { part: number | null | undefined }) {
    return <span className={`size-2.5 shrink-0 rounded-full ${part && part > 0 ? "bg-(--etat-fait)" : "border-[1.5px] border-muted-foreground"}`} />;
}

export function PageComparer({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const { vue, recharger } = useBranches(agentId);
    const [fusion, setFusion] = useState(false);
    const options = useMemo(() => {
        if (!vue) return [];
        const branches = vue.branches.map((b) => ({ valeur: `branche:${b.id}`, libelle: `${b.nom} · ${t({ en: "live", fr: "en ligne" })}` }));
        const versions = vue.branches.flatMap((b) => b.versions.map((v) => ({ valeur: `version:${v.numero}`, libelle: `${b.nom} · v${v.numero}` })));
        return [...branches, ...versions];
    }, [vue, t]);
    const [a, setA] = useState<string | null>(null);
    const [b, setB] = useState<string | null>(null);
    const [donnees, setDonnees] = useState<ComparaisonVue | null>(null);
    const [erreur, setErreur] = useState(false);

    // Départ : la principale contre la première autre branche, sinon contre sa version précédente.
    useEffect(() => {
        if (!vue || a !== null) return;
        const principale = vue.branches.find((x) => x.principale);
        const autre = vue.branches.find((x) => !x.principale);
        setA(principale ? `branche:${principale.id}` : null);
        setB(autre ? `branche:${autre.id}` : principale && principale.versions[1] ? `version:${principale.versions[1].numero}` : null);
    }, [vue, a]);

    const charger = useCallback(async () => {
        if (!a || !b || a === b) return;
        setErreur(false);
        try {
            const r = await comparerEnDuelApiV1BuilderBranchesWorkflowIdComparerGet({ path: { workflow_id: agentId }, query: { gauche: a, droite: b } });
            if (r.error || !r.data) {
                setErreur(true);
                notifier.echec(T.erreur, { erreur: r.error, groupe: "comparer" });
                return;
            }
            setDonnees(r.data);
        } catch (e) {
            setErreur(true);
            notifier.echec(T.erreur, { erreur: e, groupe: "comparer" });
        }
    }, [agentId, a, b]);

    useEffect(() => {
        if (authLoading || !user) return;
        void charger();
    }, [charger, authLoading, user]);

    const identiques = a !== null && a === b;
    // « Fusionner la deuxième dans la première » : seulement quand A est la principale et B une autre branche avec une version.
    const brancheB = vue?.branches.find((x) => b === `branche:${x.id}`);
    const principaleA = vue?.branches.find((x) => a === `branche:${x.id}`)?.principale === true;
    const peutFusionner = principaleA && !!brancheB && !brancheB.principale && brancheB.version_en_ligne !== null;
    const nom = (cle: string | null) => options.find((o) => o.valeur === cle)?.libelle ?? "";
    const familles = useMemo(() => Array.from(new Set((donnees?.configuration ?? []).map((c) => c.famille))), [donnees]);

    const verdict = donnees?.verdict;
    const phraseVerdict = () => {
        if (!donnees || !verdict) return null;
        if (verdict.gagnant === "insuffisant") return <span className="text-muted-foreground">{t(T.insuffisant)}</span>;
        if (verdict.gagnant === "egalite") return <span>{t(T.egalite)}</span>;
        const gauche = verdict.gagnant === "gauche";
        const lignes = gauche ? verdict.pour_gauche : verdict.pour_droite;
        const total = verdict.pour_gauche.length + verdict.pour_droite.length;
        const cote = gauche ? donnees.gauche : donnees.droite;
        return (
            <span data-verdict={verdict.gagnant}>
                <span className="font-semibold">{cote.nom}{cote.type === "version" ? ` v${cote.version}` : ""}</span>{" "}
                {t({ en: "does better on", fr: "fait mieux sur" })}{" "}
                <span className="font-semibold">
                    {lignes.length} {t({ en: `of ${total} measures`, fr: `mesures sur ${total}` })}
                </span>
                . <span className="text-muted-foreground">{t({ en: "On a small number of calls, to be confirmed.", fr: "Sur un petit nombre d'appels, à confirmer." })}</span>
            </span>
        );
    };

    return (
        <div className="mx-auto w-full max-w-5xl space-y-6 px-6 py-6" data-page-comparer>
            <TitrePage
                titre={t(T.titre)}
                info={t(T.info)}
                action={
                    peutFusionner ? (
                        <Button variant="outline" size="sm" onClick={() => setFusion(true)}>
                            {t({ en: "Merge the second into the first", fr: "Fusionner la deuxième dans la première" })}
                        </Button>
                    ) : undefined
                }
            />
            {fusion && brancheB && (
                <FenetreFusion
                    agentId={agentId}
                    brancheId={brancheB.id}
                    sens="fusion"
                    ouverte
                    fermer={() => setFusion(false)}
                    apres={() => {
                        void recharger();
                        setA(null);
                    }}
                />
            )}
            <div className="flex flex-wrap items-center gap-3">
                {a !== null && <Liste valeur={a} changer={setA} options={options} className="w-64" taille="default" />}
                <button
                    type="button"
                    aria-label={t(T.echanger)}
                    onClick={() => {
                        setA(b);
                        setB(a);
                    }}
                    className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:text-foreground"
                >
                    <ArrowLeftRight className="size-4" />
                </button>
                {b !== null && <Liste valeur={b} changer={setB} options={options} className="w-64" taille="default" />}
                <span className="text-sm text-muted-foreground">{t(T.periode)}</span>
            </div>

            {!vue && <EtatVide cas="chargement" lignes={4} />}
            {identiques && <p className="py-6 text-sm text-muted-foreground">{t(T.identiques)}</p>}
            {erreur && <EtatVide cas="erreur" reessayer={() => void charger()} />}
            {donnees && !identiques && !erreur && (
                <>
                    <section className="space-y-3">
                        <div className="grid grid-cols-[1fr_auto_1fr] items-stretch gap-3">
                            {([["gauche", donnees.gauche, T.coteA], ["droite", donnees.droite, T.coteB]] as const).map(([cle, cote, titre], i) => {
                                const appels = donnees.mesures.find((m) => m.cle === "appels")?.[cle];
                                return (
                                    <div key={cle} className={`rounded-xl border bg-card px-5 py-4 ${i === 1 ? "order-3" : ""}`} data-cote={cle}>
                                        <p className="text-xs text-muted-foreground">{t(titre)}</p>
                                        <p className="mt-1 flex items-center gap-2 text-base font-semibold">
                                            <PointBranche part={cote.part} />
                                            {nom(cote.type === "branche" ? `branche:${cote.id}` : `version:${cote.version}`) || cote.nom}
                                        </p>
                                        <p className="mt-1 text-sm text-muted-foreground">
                                            {cote.part !== null && cote.part !== undefined ? `${cote.part} % ${t(T.traffic)} · ` : ""}
                                            {appels ?? 0} {t(T.appels)}
                                        </p>
                                    </div>
                                );
                            })}
                            <span className="order-2 self-center text-xs font-medium text-muted-foreground">{t(T.contre)}</span>
                        </div>
                        <p className="text-sm">{phraseVerdict()}</p>
                    </section>

                    <section>
                        <TitreTableau titre={t(T.resultats)} info={<Info>{t(T.resultatsInfo)}</Info>} />
                        <Tableau colonnes={[{ titre: t(T.mesure) }, { titre: "A", droite: true }, { titre: "B", droite: true }, { titre: t(T.ecart) }]}>
                            {donnees.mesures.map((m) => {
                                const e = ecartDe(m);
                                const Fleche = !e || e.signe === 0 ? Minus : e.signe > 0 ? ArrowUp : ArrowDown;
                                const max = Math.max(Math.abs(m.gauche ?? 0), Math.abs(m.droite ?? 0)) || 1;
                                const teinte = !m.meilleur ? "text-muted-foreground" : "text-(--meilleur-texte)";
                                return (
                                    <Ligne key={m.cle}>
                                        <Cellule principale>{t(MESURES[m.cle] ?? { en: m.cle, fr: m.cle })}</Cellule>
                                        {(["gauche", "droite"] as const).map((cote) => (
                                            <Cellule key={cote} droite>
                                                <span
                                                    data-meilleur={m.meilleur === cote ? "oui" : undefined}
                                                    className={`inline-flex rounded-md px-2 py-0.5 tabular-nums ${m.meilleur === cote ? "bg-(--meilleur-fond) font-semibold text-(--meilleur-texte)" : ""}`}
                                                >
                                                    {formater(m.cle, m[cote])}
                                                </span>
                                            </Cellule>
                                        ))}
                                        <Cellule>
                                            {e ? (
                                                <span className="flex items-center gap-3">
                                                    <span className={`inline-flex w-28 items-center gap-1 text-sm font-medium tabular-nums ${m.meilleur ? (m.meilleur === "droite" ? "text-(--meilleur-texte)" : "text-(--ecart-mal)") : "text-muted-foreground"}`}>
                                                        <Fleche className="size-3.5" />
                                                        {e.texte}
                                                    </span>
                                                    <span className="flex h-1.5 w-28 overflow-hidden rounded-full bg-muted" aria-hidden>
                                                        <span
                                                            className={`h-full rounded-full ${m.meilleur ? (m.meilleur === "droite" ? "bg-(--etat-fait)" : "bg-destructive") : "bg-muted-foreground/40"}`}
                                                            style={{ width: `${Math.round((Math.abs(m.droite ?? 0) / max) * 100)}%` }}
                                                        />
                                                    </span>
                                                </span>
                                            ) : (
                                                <span className={teinte}>–</span>
                                            )}
                                        </Cellule>
                                    </Ligne>
                                );
                            })}
                        </Tableau>
                    </section>

                    <section>
                        <TitreTableau titre={t(T.config)} info={<Info>{t(T.configInfo)}</Info>} />
                        {donnees.configuration.length === 0 ? (
                            <p className="py-6 text-sm text-muted-foreground">{t(T.aucuneDiff)}</p>
                        ) : (
                            familles.map((f) => <FamilleDiff key={f} famille={f} lignes={donnees.configuration.filter((c) => c.famille === f)} />)
                        )}
                    </section>
                </>
            )}
        </div>
    );
}

function FamilleDiff({ famille, lignes }: { famille: string; lignes: LigneDeConfiguration[] }) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(true);
    return (
        <div className="pt-4" data-famille={famille}>
            <button
                type="button"
                onClick={() => setOuvert(!ouvert)}
                aria-expanded={ouvert}
                className="flex w-full cursor-pointer items-center gap-2 pb-2 text-sm font-medium hover:font-semibold"
            >
                <ChevronDown className={`size-4 text-muted-foreground transition-transform ${ouvert ? "" : "-rotate-90"}`} />
                {t(FAMILLES[famille] ?? { en: famille, fr: famille })}
                <span className="text-xs font-normal text-muted-foreground">
                    {lignes.length} {lignes.length > 1 ? t({ en: "changes", fr: "changements" }) : t({ en: "change", fr: "changement" })}
                </span>
            </button>
            {ouvert && (
                <ul className="divide-y">
                    {lignes.map((c) => (
                        <li key={c.cle} className="py-3">
                            <p className="pb-1.5 text-sm font-medium">{c.libelle}</p>
                            <p className="flex gap-2 rounded-md bg-(--ecart-mal-fond) px-3 py-1.5 text-sm text-(--ecart-mal)">
                                <span className="font-mono">−</span>
                                <span className="line-through decoration-current/40 break-words">{c.avant ?? t(T.absent)}</span>
                            </p>
                            <p className="mt-1 flex gap-2 rounded-md bg-(--meilleur-fond) px-3 py-1.5 text-sm text-(--meilleur-texte)">
                                <span className="font-mono">+</span>
                                <span className="break-words">{c.apres ?? t(T.absent)}</span>
                            </p>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
