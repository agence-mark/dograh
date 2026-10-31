"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): create a test. Three ways in, one form:
 *  - from a reply of a call (`source`: the page of a call and the « To triage » page open it with the run and the reply's rank),
 *  - by hand: a reply and its history, or a free conversation with a caller character,
 *  - the builder writes them from the client sheet through the same server function.
 * Personal data is replaced by fake data by the server before anything is kept (Q3); the form says so.
 */
import { useState } from "react";

import { creerUnTestApiV1BuilderTestsWorkflowIdPost } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { type ChampDeCritere, CHAMPS, CRITERES, ORIGINES_DE_TEST } from "./libelles";

const CHAMP = "w-full rounded-md border bg-background px-2 py-1.5 text-sm";

export interface SourceDuTest {
    runId: number;
    /** The caller's reply at fault, counted from 1. */
    rang: number;
    extrait?: string;
}

interface LigneDeCritere {
    type: string;
    valeurs: Partial<Record<ChampDeCritere, string | boolean>>;
}

interface Props {
    workflowId: number;
    source?: SourceDuTest;
    onCree: (slug: string) => void;
    onFermer?: () => void;
}

const liste = (v: unknown) =>
    String(v ?? "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);

/** The criterion the server expects, from a form line. */
export function critereDeLaLigne(ligne: LigneDeCritere): Record<string, unknown> {
    const v = ligne.valeurs;
    const c: Record<string, unknown> = { type: ligne.type };
    if (v.texte !== undefined) c.texte = String(v.texte).trim();
    if (ligne.type === "outil") {
        c.nom = String(v.nom ?? "").trim();
        if (v.ne_doit_pas_etre_appele) c.appele = false;
    }
    if (v.attendue !== undefined) c.attendue = String(v.attendue).trim();
    if (v.noms !== undefined) c.noms = liste(v.noms);
    if (v.champs !== undefined) c.champs = liste(v.champs);
    if (v.max !== undefined) c.max = Number(v.max) || 0;
    return c;
}

export function NouveauTest({ workflowId, source, onCree, onFermer }: Props) {
    const { t } = useLangue();
    const [nom, setNom] = useState("");
    const [genre, setGenre] = useState<"replique" | "conversation">("replique");
    const [replique, setReplique] = useState("");
    const [scenario, setScenario] = useState("");
    const [personnage, setPersonnage] = useState("");
    const [ouverture, setOuverture] = useState("");
    const [obligatoire, setObligatoire] = useState(false);
    const [dossier, setDossier] = useState("");
    const [origine, setOrigine] = useState(source ? "client" : "manuel");
    const [criteres, setCriteres] = useState<LigneDeCritere[]>([{ type: "texte_absent", valeurs: { texte: "" } }]);
    const [erreur, setErreur] = useState<string | null>(null);
    const [envoi, setEnvoi] = useState(false);

    const changerType = (i: number, type: string) =>
        setCriteres((avant) => avant.map((c, k) => (k === i ? { type, valeurs: Object.fromEntries(CRITERES[type].champs.map((ch) => [ch, ch === "ne_doit_pas_etre_appele" ? false : ""])) } : c)));
    const changerValeur = (i: number, champ: ChampDeCritere, valeur: string | boolean) =>
        setCriteres((avant) => avant.map((c, k) => (k === i ? { ...c, valeurs: { ...c.valeurs, [champ]: valeur } } : c)));

    const pret = nom.trim() && criteres.length > 0 && (source ? true : genre === "replique" ? replique.trim() : scenario.trim());

    const envoyer = async () => {
        setEnvoi(true);
        const corps: Record<string, unknown> = {
            nom: nom.trim(),
            criteres: criteres.map(critereDeLaLigne),
            obligatoire,
            dossier: dossier.trim(),
            origine,
        };
        if (source) Object.assign(corps, { run_id: source.runId, rang: source.rang });
        else if (genre === "replique") corps.replique = replique.trim();
        else Object.assign(corps, { scenario: scenario.trim(), personnage: personnage.trim() || null, ouverture: ouverture.trim() || null });
        const reponse = await creerUnTestApiV1BuilderTestsWorkflowIdPost({ path: { workflow_id: workflowId }, body: corps as never });
        setEnvoi(false);
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The test was not created"));
            return;
        }
        setErreur(null);
        onCree(((reponse.data as { test?: { slug?: string } }).test?.slug ?? "") as string);
    };

    return (
        <section className="space-y-3 rounded border p-4" data-testid="nouveau-test">
            <h2 className="text-lg font-semibold">{t({ en: "New test", fr: "Nouveau test" })}</h2>
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "Personal data is replaced by fake data before the test is kept. The code judges the criteria; a required test that fails blocks the publication.",
                    fr: "Les données personnelles sont remplacées par des fausses avant d'enregistrer le test. Le code juge les critères ; un test obligatoire qui échoue bloque la publication.",
                })}
            </p>
            <label className="block space-y-1 text-sm">
                <span>{t({ en: "Name", fr: "Nom" })}</span>
                <input className={CHAMP} value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Test name", fr: "Nom du test" })} />
            </label>
            {source ? (
                <p className="rounded bg-muted p-2 text-sm" data-testid="source-du-test">
                    {t({ en: "From call", fr: "Depuis l'appel" })} n° {source.runId}, {t({ en: "reply", fr: "réplique" })} {source.rang}
                    {source.extrait ? ` : « ${source.extrait} »` : ""}
                </p>
            ) : (
                <>
                    <div className="flex gap-4 text-sm">
                        <label className="flex items-center gap-1">
                            <input type="radio" checked={genre === "replique"} onChange={() => setGenre("replique")} />
                            {t({ en: "One reply", fr: "Une réplique" })}
                        </label>
                        <label className="flex items-center gap-1">
                            <input type="radio" checked={genre === "conversation"} onChange={() => setGenre("conversation")} />
                            {t({ en: "Free conversation (simulated caller)", fr: "Conversation libre (appelant simulé)" })}
                        </label>
                    </div>
                    {genre === "replique" ? (
                        <label className="block space-y-1 text-sm">
                            <span>{t({ en: "The person's reply", fr: "La réplique de la personne" })}</span>
                            <textarea className={CHAMP} rows={2} value={replique} onChange={(e) => setReplique(e.target.value)} aria-label={t({ en: "Reply", fr: "Réplique" })} />
                        </label>
                    ) : (
                        <div className="grid gap-3 md:grid-cols-3">
                            <label className="block space-y-1 text-sm md:col-span-3">
                                <span>{t({ en: "What the caller wants", fr: "Ce que l'appelant veut" })}</span>
                                <textarea className={CHAMP} rows={2} value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label={t({ en: "Scenario", fr: "Scénario" })} />
                            </label>
                            <label className="block space-y-1 text-sm">
                                <span>{t({ en: "Caller character (library)", fr: "Personnage d'appelant (bibliothèque)" })}</span>
                                <input className={CHAMP} value={personnage} onChange={(e) => setPersonnage(e.target.value)} placeholder="slug" />
                            </label>
                            <label className="block space-y-1 text-sm md:col-span-2">
                                <span>{t({ en: "First words", fr: "Premiers mots" })}</span>
                                <input className={CHAMP} value={ouverture} onChange={(e) => setOuverture(e.target.value)} />
                            </label>
                        </div>
                    )}
                </>
            )}
            <div className="space-y-2" data-testid="criteres-du-test">
                <h3 className="text-sm font-medium">{t({ en: "Criteria (judged by the code)", fr: "Critères (jugés par le code)" })}</h3>
                {criteres.map((c, i) => (
                    <div key={i} className="flex flex-wrap items-end gap-2">
                        <select
                            aria-label={t({ en: "Criterion", fr: "Critère" })}
                            className="h-9 rounded-md border bg-background px-2 text-sm"
                            value={c.type}
                            onChange={(e) => changerType(i, e.target.value)}
                        >
                            {Object.entries(CRITERES).map(([type, d]) => (
                                <option key={type} value={type}>
                                    {t(d.libelle)}
                                </option>
                            ))}
                        </select>
                        {CRITERES[c.type].champs.map((ch) =>
                            ch === "ne_doit_pas_etre_appele" ? (
                                <label key={ch} className="flex items-center gap-1 text-sm">
                                    <input type="checkbox" checked={Boolean(c.valeurs[ch])} onChange={(e) => changerValeur(i, ch, e.target.checked)} />
                                    {t(CHAMPS[ch])}
                                </label>
                            ) : (
                                <input
                                    key={ch}
                                    className="h-9 rounded-md border bg-background px-2 text-sm"
                                    aria-label={t(CHAMPS[ch])}
                                    placeholder={t(CHAMPS[ch])}
                                    value={String(c.valeurs[ch] ?? "")}
                                    onChange={(e) => changerValeur(i, ch, e.target.value)}
                                />
                            ),
                        )}
                        {criteres.length > 1 && (
                            <Button variant="ghost" size="sm" onClick={() => setCriteres((avant) => avant.filter((_, k) => k !== i))}>
                                {t({ en: "Remove", fr: "Retirer" })}
                            </Button>
                        )}
                    </div>
                ))}
                <Button variant="outline" size="sm" onClick={() => setCriteres((avant) => [...avant, { type: "texte_absent", valeurs: { texte: "" } }])}>
                    {t({ en: "Add a criterion", fr: "Ajouter un critère" })}
                </Button>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="flex items-center gap-2">
                    <input type="checkbox" checked={obligatoire} onChange={(e) => setObligatoire(e.target.checked)} aria-label={t({ en: "Required", fr: "Obligatoire" })} />
                    {t({ en: "Required (blocks the publication)", fr: "Obligatoire (bloque la publication)" })}
                </label>
                <label className="flex items-center gap-2">
                    <span>{t({ en: "Folder", fr: "Dossier" })}</span>
                    <input className="h-9 rounded-md border bg-background px-2" value={dossier} onChange={(e) => setDossier(e.target.value)} />
                </label>
                <label className="flex items-center gap-2">
                    <span>{t({ en: "Origin", fr: "Origine" })}</span>
                    <select className="h-9 rounded-md border bg-background px-2" value={origine} onChange={(e) => setOrigine(e.target.value)}>
                        {Object.entries(ORIGINES_DE_TEST).map(([valeur, libelle]) => (
                            <option key={valeur} value={valeur}>
                                {t(libelle)}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            <div className="flex gap-2">
                <Button disabled={!pret || envoi} onClick={() => void envoyer()}>
                    {t({ en: "Create the test", fr: "Créer le test" })}
                </Button>
                {onFermer && (
                    <Button variant="ghost" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                )}
            </div>
        </section>
    );
}
