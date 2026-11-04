"use client";

/**
 * [.mark] U8 : le détail d'un problème de « À améliorer » (E23), repris de `DetailProbleme` de la maquette : à gauche d'où il vient,
 * les cas regroupés, la réplique fautive, la cause ; à droite la correction proposée (seulement si le builder en a posé une),
 * l'avancement et les gestes. Rien d'inventé : chaque ligne vient de `GET /ameliorations/{id}`, chaque geste d'une route réelle.
 * Forme non prévue par la maquette (provisoire, E-G1-2) : la personne chargée et l'origine se changent ici, comme dans l'ancien « À trier ».
 */
import { Check, Circle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
    changerUneAmeliorationApiV1AmeliorationsAmeliorationIdPut,
    creerUnTestDepuisLaRepliqueApiV1AmeliorationsAmeliorationIdTestPost,
    lireLesPersonnesAssignablesApiV1TriPersonnesGet,
    lireUneAmeliorationApiV1AmeliorationsAmeliorationIdGet,
    ouvrirUnFilApiV1BuilderFilsPost,
    rejouerLaSuiteDeLAgentApiV1AmeliorationsAmeliorationIdRejouerPost,
} from "@/client";
import type { VueDetaillee } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Gravite, Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { AUTEUR, CAUSES, demandeAuBuilder, ORIGINES, TEMPS_DE_L_AVANCEMENT, texteDeFrequence, titreLisible } from "./libelles";

const T = {
    dOuIlVient: { en: "Where it comes from", fr: "D'où il vient" },
    controle: { en: "Check or criterion: ", fr: "Contrôle ou critère : " },
    cas: { en: "Grouped cases", fr: "Cas regroupés" },
    casInfo: {
        en: "Same agent, same criterion or check, same step: one problem, counted.",
        fr: "Même agent, même critère ou contrôle, même étape : un seul problème, compté.",
    },
    ouvrir: { en: "open", fr: "ouvrir" },
    replique: { en: "Faulty reply", fr: "Réplique fautive" },
    cause: { en: "Probable cause", fr: "Cause probable" },
    causeInfo: {
        en: "Read from the traces of the call, with the judge's confidence; an uncertain cause is checked before fixing.",
        fr: "Lue dans les traces de l'appel, avec la confiance du juge ; une cause incertaine se vérifie avant de corriger.",
    },
    confiance: { en: "confidence", fr: "confiance" },
    origine: { en: "Origin", fr: "Origine" },
    origineInfo: {
        en: "Where the fix belongs: the client's sheet (this agent only), a library recipe (every following agent) or the code of the fork.",
        fr: "Où la correction se range : la fiche du client (cet agent seulement), une recette de la bibliothèque (tous les agents suivants) ou le code du fork.",
    },
    suggeree: { en: "suggested", fr: "suggérée" },
    chargeDe: { en: "Assigned to", fr: "Assigné à" },
    personne: { en: "Nobody", fr: "Personne" },
    recettes: { en: "Recipes this agent uses", fr: "Recettes que cet agent utilise" },
    recettesInfo: {
        en: "The change is proposed to the library, then proven on a bench: every following agent benefits.",
        fr: "Le changement se propose à la bibliothèque, puis se prouve sur un banc : tous les agents suivants en profitent.",
    },
    bibliotheque: { en: "Open the library", fr: "Ouvrir la bibliothèque" },
    correction: { en: "Correction proposed by the builder", fr: "Correction proposée par le builder" },
    avancement: { en: "Progress", fr: "Avancement" },
    creerTest: { en: "Create a test from the reply", fr: "Créer un test depuis la réplique" },
    rejouer: { en: "Replay the suite", fr: "Rejouer la suite" },
    discuter: { en: "Discuss with the builder", fr: "Discuter avec le builder" },
    ecouter: { en: "Listen to the call", fr: "Écouter l'appel" },
    ignorer: { en: "Ignore", fr: "Ignorer" },
    fermer: { en: "Close", fr: "Fermer" },
    test: { en: "test", fr: "test" },
    essais: { en: "attempts", fr: "essais" },
    revoir: { en: "passed, to review", fr: "réussi, à revoir" },
};

const MESSAGES = {
    testCree: { en: "Test created from the reply.", fr: "Test créé depuis la réplique." },
    testEchec: { en: "Test not created. Check its criteria and try again.", fr: "Test non créé. Vérifiez ses critères et réessayez." },
    suiteVerte: { en: "Suite replayed: all green, the problem is tested.", fr: "Suite rejouée : tout est vert, le problème est testé." },
    suiteRouge: { en: "Suite replayed: some tests still fail.", fr: "Suite rejouée : des tests échouent encore." },
    suiteEchec: { en: "Suite not replayed. Try again.", fr: "Suite non rejouée. Réessayez." },
    suiteEnCours: { en: "Replaying the suite…", fr: "Rejeu de la suite…" },
    ignore: { en: "Problem ignored.", fr: "Problème ignoré." },
    ignoreEchec: { en: "Problem not ignored. Try again.", fr: "Problème non ignoré. Réessayez." },
    builderEchec: { en: "The conversation could not be opened. Try again.", fr: "La conversation n'a pas pu être ouverte. Réessayez." },
    changeEchec: { en: "Change not saved. Try again.", fr: "Changement non enregistré. Réessayez." },
};

type Personne = { id: number; nom: string };
type Cas = { run_id?: number | null; test?: string | null; le?: string | null; reussis?: number | null; total?: number | null; a_revoir?: boolean | null };

export function DetailProbleme({ id, fermer, apres }: { id: number; fermer: () => void; apres: () => void }) {
    const { t, langue } = useLangue();
    const router = useRouter();
    const [vue, setVue] = useState<VueDetaillee | null | "erreur">(null);
    const [personnes, setPersonnes] = useState<Personne[]>([]);
    const [occupe, setOccupe] = useState(false);

    const charger = useCallback(async () => {
        const r = await lireUneAmeliorationApiV1AmeliorationsAmeliorationIdGet({ path: { amelioration_id: id } });
        setVue(r.error || !r.data ? "erreur" : r.data);
    }, [id]);

    useEffect(() => {
        void charger();
        void lireLesPersonnesAssignablesApiV1TriPersonnesGet().then((r) => {
            if (!r.error && Array.isArray(r.data)) setPersonnes(r.data as Personne[]);
        });
    }, [charger]);

    const changer = async (corps: { etat?: "a_trier" | "en_cours" | "ignoree"; assigne?: number | null; origine?: "client" | "recette" | "code" }) => {
        const r = await changerUneAmeliorationApiV1AmeliorationsAmeliorationIdPut({ path: { amelioration_id: id }, body: corps });
        if (r.error || !r.data) {
            notifier.echec(MESSAGES.changeEchec, { erreur: r.error });
            return false;
        }
        setVue(r.data);
        apres();
        return true;
    };

    const creerLeTest = async () => {
        setOccupe(true);
        const r = await creerUnTestDepuisLaRepliqueApiV1AmeliorationsAmeliorationIdTestPost({ path: { amelioration_id: id }, body: {} });
        setOccupe(false);
        if (r.error) return void notifier.echec(MESSAGES.testEchec, { erreur: r.error });
        notifier.succes(MESSAGES.testCree);
        await charger();
    };

    const rejouer = async () => {
        setOccupe(true);
        const cours = notifier.enCours(MESSAGES.suiteEnCours);
        const r = await rejouerLaSuiteDeLAgentApiV1AmeliorationsAmeliorationIdRejouerPost({ path: { amelioration_id: id } });
        setOccupe(false);
        if (r.error || !r.data) return void cours.echec(MESSAGES.suiteEchec, { erreur: r.error, reessayer: () => void rejouer() });
        if (r.data.ok && r.data.suite_complete) cours.succes(MESSAGES.suiteVerte);
        else cours.echec(MESSAGES.suiteRouge, { erreur: new Error(`${r.data.reussis}/${r.data.total}`) });
        await charger();
        apres();
    };

    const discuter = async () => {
        if (!vue || vue === "erreur") return;
        const r = await ouvrirUnFilApiV1BuilderFilsPost({
            body: { message: demandeAuBuilder({ ...vue, id }), workflow_id: vue.workflow_id, demarrage: null },
        });
        if (r.error || !r.data) return void notifier.echec(MESSAGES.builderEchec, { erreur: r.error });
        router.push(`/labo/builder/${r.data.id}`);
    };

    const ignorer = async () => {
        if (!(await changer({ etat: "ignoree" }))) return;
        const retour = vue && vue !== "erreur" ? vue.etat : "a_trier";
        notifier.reversible(MESSAGES.ignore, async () => {
            const r = await changerUneAmeliorationApiV1AmeliorationsAmeliorationIdPut({
                path: { amelioration_id: id },
                body: { etat: retour === "en_cours" ? "en_cours" : "a_trier" },
            });
            if (r.error) notifier.echec(MESSAGES.ignoreEchec, { erreur: r.error });
            apres();
        });
        fermer();
    };

    const cas = (vue && vue !== "erreur" ? vue.cas : []) as Cas[];
    const correction = (vue && vue !== "erreur" ? vue.correction : null) as { avant?: string; apres?: string; etape?: string; cible?: string } | null;
    const premierCasAvecAppel = cas.find((c) => c.run_id);

    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent className="sm:max-w-3xl" onOpenAutoFocus={(e) => e.preventDefault()}>
                {vue === null || vue === "erreur" ? (
                    <>
                        <DialogHeader>
                            <DialogTitle className="sr-only">{t({ en: "Problem", fr: "Problème" })}</DialogTitle>
                        </DialogHeader>
                        {vue === null ? <EtatVide cas="chargement" lignes={4} /> : <EtatVide cas="erreur" reessayer={() => void charger()} />}
                    </>
                ) : (
                    <>
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Gravite n={vue.gravite as 1 | 2 | 3} />
                                {(() => {
                                    const titre = titreLisible(vue);
                                    return typeof titre === "string" ? titre : t(titre);
                                })()}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="grid max-h-[65vh] gap-5 overflow-auto text-sm md:grid-cols-2">
                            <div className="space-y-4">
                                <div className="space-y-1">
                                    <p className="font-medium">{t(T.dOuIlVient)}</p>
                                    <p className="text-muted-foreground">{t(AUTEUR[vue.releve_par] ?? AUTEUR.code)}</p>
                                    <p>
                                        {t(T.controle)}
                                        <span className="font-medium">{vue.critere ?? ""}</span>
                                        {" · "}
                                        {texteDeFrequence(vue, t)}
                                    </p>
                                </div>
                                <div className="space-y-1">
                                    <p className="flex items-center gap-1.5 font-medium">
                                        {t(T.cas)}
                                        <Info>{t(T.casInfo)}</Info>
                                    </p>
                                    <ul className="divide-y">
                                        {cas.map((c, i) => (
                                            <li key={`${c.run_id ?? c.test}-${i}`} className="flex items-center py-2">
                                                <span className="flex-1">
                                                    {c.run_id ? `n° ${c.run_id}` : `${t(T.test)} ${c.test ?? ""}${c.reussis != null && c.total ? ` · ${c.a_revoir ? t(T.revoir) : `${c.reussis}/${c.total}`}` : ""}`}
                                                    {" · "}
                                                    <DateRelative valeur={c.le} />
                                                </span>
                                                {c.run_id && (
                                                    <Link href={`/workflow/${vue.workflow_id}/run/${c.run_id}`} className="cursor-pointer text-xs text-(--acc-text) hover:font-medium">
                                                        {t(T.ouvrir)}
                                                    </Link>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                {vue.replique && (
                                    <div className="space-y-1">
                                        <p className="font-medium">{t(T.replique)}</p>
                                        <p className="rounded-lg bg-muted/50 px-3 py-2">« {vue.replique} »</p>
                                    </div>
                                )}
                                {vue.cause && (
                                    <div className="space-y-1">
                                        <p className="flex items-center gap-1.5 font-medium">
                                            {t(T.cause)}
                                            <Info>{t(T.causeInfo)}</Info>
                                        </p>
                                        <p>
                                            {CAUSES[vue.cause] ? t(CAUSES[vue.cause]) : vue.cause}
                                            {vue.confiance != null && ` · ${t(T.confiance)} ${String(vue.confiance.toFixed(2)).replace(".", ",")}`}
                                        </p>
                                    </div>
                                )}
                                <div className="space-y-1">
                                    <p className="flex items-center gap-1.5 font-medium">
                                        {t(T.origine)}
                                        <Info>{t(T.origineInfo)}</Info>
                                    </p>
                                    <div className="flex flex-wrap items-center gap-3">
                                        <ListeDeroulante
                                            aria-label={t(T.origine)}
                                            className="h-8 cursor-pointer rounded-md border bg-background px-2 text-sm"
                                            value={vue.origine ?? ""}
                                            onChange={(e) => e.target.value && void changer({ origine: e.target.value as "client" | "recette" | "code" })}
                                        >
                                            <option value="">
                                                {t(ORIGINES[vue.origine_suggeree])} ({t(T.suggeree)})
                                            </option>
                                            {Object.entries(ORIGINES).map(([cle, libelle]) => (
                                                <option key={cle} value={cle}>
                                                    {t(libelle)}
                                                </option>
                                            ))}
                                        </ListeDeroulante>
                                        <ListeDeroulante
                                            aria-label={t(T.chargeDe)}
                                            className="h-8 cursor-pointer rounded-md border bg-background px-2 text-sm"
                                            value={vue.assigne ?? ""}
                                            onChange={(e) => void changer({ assigne: e.target.value === "" ? null : Number(e.target.value) })}
                                        >
                                            <option value="">{t(T.personne)}</option>
                                            {personnes.map((p) => (
                                                <option key={p.id} value={p.id}>
                                                    {p.nom}
                                                </option>
                                            ))}
                                        </ListeDeroulante>
                                    </div>
                                </div>
                                {(vue.origine ?? vue.origine_suggeree) === "recette" && vue.recettes.length > 0 && (
                                    <div className="space-y-1">
                                        <p className="flex items-center gap-1.5 font-medium">
                                            {t(T.recettes)}
                                            <Info>{t(T.recettesInfo)}</Info>
                                        </p>
                                        <ul className="divide-y">
                                            {(vue.recettes as { famille: string; slug: string; version?: number | null }[]).map((r) => (
                                                <li key={`${r.famille}:${r.slug}`} className="flex items-center py-2">
                                                    <span className="flex-1">{`${r.famille} · ${r.slug}`}</span>
                                                    {r.version != null && <span className="text-xs text-muted-foreground">v{r.version}</span>}
                                                </li>
                                            ))}
                                        </ul>
                                        <Link href="/labo/bibliotheque" className="inline-block cursor-pointer text-xs text-(--acc-text) hover:font-medium">
                                            {t(T.bibliotheque)}
                                        </Link>
                                    </div>
                                )}
                            </div>
                            <div className="space-y-4">
                                {correction && (
                                    <div className="space-y-2">
                                        <p className="font-medium">{t(T.correction)}</p>
                                        <div className="rounded-lg border font-mono text-xs">
                                            <p className="bg-(--marque-danger) px-3 py-2 text-(--marque-danger-texte)">- {correction.avant ?? ""}</p>
                                            <p className="bg-(--marque-succes) px-3 py-2 text-(--marque-succes-texte)">+ {correction.apres ?? ""}</p>
                                        </div>
                                        {(correction.etape || correction.cible) && (
                                            <p className="text-xs text-muted-foreground">
                                                {[correction.etape, correction.cible, `${vue.workflow_nom}${vue.version ? ` v${vue.version}` : ""}`].filter(Boolean).join(" · ")}
                                            </p>
                                        )}
                                    </div>
                                )}
                                <div className="space-y-2">
                                    <p className="font-medium">{t(T.avancement)}</p>
                                    <ol className="space-y-1.5">
                                        {vue.avancement.map((a) => (
                                            <li key={String(a.temps)} className={`flex items-center gap-2 ${a.fait ? "" : "text-muted-foreground"}`}>
                                                {a.fait ? <Check className="size-4 text-(--etat-fait)" /> : <Circle className="size-4 text-black/20" />}
                                                {t(TEMPS_DE_L_AVANCEMENT[String(a.temps)])}
                                            </li>
                                        ))}
                                    </ol>
                                </div>
                                <div className="flex flex-wrap gap-2 pt-2">
                                    {!vue.avancement.find((a) => a.temps === "test_cree")?.fait && premierCasAvecAppel && (
                                        <Button size="sm" disabled={occupe} onClick={() => void creerLeTest()}>
                                            {t(T.creerTest)}
                                        </Button>
                                    )}
                                    <Button size="sm" variant={vue.avancement.find((a) => a.temps === "test_cree")?.fait ? "default" : "outline"} disabled={occupe} onClick={() => void rejouer()}>
                                        {t(T.rejouer)}
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => void discuter()}>
                                        {t(T.discuter)}
                                    </Button>
                                    {premierCasAvecAppel && (
                                        <Button size="sm" variant="outline" asChild>
                                            <Link href={`/workflow/${vue.workflow_id}/run/${premierCasAvecAppel.run_id}`}>{t(T.ecouter)}</Link>
                                        </Button>
                                    )}
                                    <Button size="sm" variant="ghost" className="text-muted-foreground" onClick={() => void ignorer()}>
                                        {t(T.ignorer)}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
}
