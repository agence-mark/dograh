"use client";

/**
 * [.mark] U3 (E47): the window of a test, three kinds: a simulated conversation, the next reply, a tool call. Settings on the
 * left, the conversation (editable) on the right, a fixed foot: folder, required, delete, create, create and play.
 * Creating and changing go through the same server function as the builder's actions. Every list (steps, tools, outcomes,
 * characters) is read from the agent and the library; nothing is written in the screen.
 */
import { useState } from "react";

import {
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch,
    creerUnTestApiV1BuilderTestsWorkflowIdPost,
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost,
} from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { EditeurDeCriteres, ligneDuCritere, ligneVide } from "./EditeurDeCriteres";
import { critereDeLaLigne, type LigneDeCritere } from "./NouveauTest";
import { type RessourcesDeTest, type SorteDeTest, sorteDuTest, type TestComplet } from "./types";

type Message = { role: "user" | "assistant"; texte: string };

const SORTES: Array<{ id: SorteDeTest; fr: string; en: string; info: { fr: string; en: string } }> = [
    {
        id: "conversation",
        fr: "Conversation simulée",
        en: "Simulated conversation",
        info: { fr: "Un appelant simulé joue le scénario avec l'agent, puis le code juge les critères.", en: "A simulated caller plays the scenario with the agent, then the code judges the criteria." },
    },
    {
        id: "replique",
        fr: "Réplique suivante",
        en: "Next reply",
        info: { fr: "L'historique est donné ; on rejoue un seul tour et on juge la réponse de l'agent.", en: "The history is given; one turn is replayed and the agent's answer is judged." },
    },
    {
        id: "outil",
        fr: "Appel d'outil",
        en: "Tool call",
        info: { fr: "Comme la réplique suivante, mais le critère est l'appel (ou le non-appel) d'un outil de l'agent.", en: "Like the next reply, but the criterion is a call (or no call) to one of the agent's tools." },
    },
];

export function FenetreDeTest({
    workflowId,
    test,
    ressources,
    onFermer,
    onFait,
    onSupprimer,
}: {
    workflowId: number;
    test?: TestComplet;
    ressources: RessourcesDeTest | null;
    onFermer: () => void;
    /** `slug` of the test written; `jouer` when « and play » was chosen. */
    onFait: (slug: string, jouer: boolean) => void;
    onSupprimer?: () => void;
}) {
    const { t } = useLangue();
    const [sorte, setSorte] = useState<SorteDeTest>(test ? sorteDuTest(test) : "conversation");
    const [nom, setNom] = useState(test?.nom ?? "");
    const [description, setDescription] = useState(test?.description ?? "");
    const [dossier, setDossier] = useState(test?.dossier ?? "");
    const [obligatoire, setObligatoire] = useState(test?.obligatoire ?? false);
    const [criteres, setCriteres] = useState<LigneDeCritere[]>(test ? test.criteres.map(ligneDuCritere) : [ligneVide()]);
    const [replique, setReplique] = useState(test?.replique ?? "");
    const [historique, setHistorique] = useState<Message[]>((test?.historique ?? []) as Message[]);
    const [scenario, setScenario] = useState(test?.scenario?.but ?? "");
    const [personnage, setPersonnage] = useState(test?.scenario?.personnage ?? "");
    const [ouverture, setOuverture] = useState(test?.scenario?.ouverture ?? "");
    const [tours, setTours] = useState(test?.scenario?.tours_max ? String(test.scenario.tours_max) : "");
    const [questions, setQuestions] = useState(((test as { questions_juge?: string[] } | undefined)?.questions_juge ?? []).join("\n"));
    const [erreur, setErreur] = useState<string | null>(null);
    const [envoi, setEnvoi] = useState(false);

    const changerSorte = (s: SorteDeTest) => {
        setSorte(s);
        setCriteres([s === "outil" ? ligneVide("outil") : ligneVide()]);
    };

    const typesOfferts = sorte === "outil" ? ["outil"] : undefined;
    const pret = nom.trim() !== "" && criteres.length > 0 && (sorte === "conversation" ? scenario.trim() !== "" : replique.trim() !== "");

    const envoyer = async (jouer: boolean) => {
        setEnvoi(true);
        setErreur(null);
        const commun = {
            nom: nom.trim(),
            description: description.trim(),
            criteres: criteres.map(critereDeLaLigne),
            obligatoire,
            dossier: dossier.trim(),
            questions_juge: questions
                .split("\n")
                .map((q) => q.trim())
                .filter(Boolean),
        };
        const propre =
            sorte === "conversation"
                ? { scenario: scenario.trim(), personnage: personnage || null, ouverture: ouverture.trim() || null, tours_max: Number(tours) || null }
                : { replique: replique.trim(), historique: historique.filter((m) => m.texte.trim()) };
        const corps = { ...commun, ...propre };
        let slug = test?.slug ?? "";
        if (test) {
            const r = await changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch({ path: { workflow_id: workflowId, slug: test.slug }, body: corps as never });
            if (r.error) {
                setEnvoi(false);
                setErreur(detailFromError(r.error, "The test was not changed"));
                return;
            }
        } else {
            const r = await creerUnTestApiV1BuilderTestsWorkflowIdPost({ path: { workflow_id: workflowId }, body: { ...corps, origine: "manuel" } as never });
            if (r.error || !r.data) {
                setEnvoi(false);
                setErreur(detailFromError(r.error, "The test was not created"));
                return;
            }
            slug = ((r.data as { test?: { slug?: string } }).test?.slug ?? "") as string;
        }
        if (jouer) await rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost({ path: { workflow_id: workflowId }, body: { tests: [slug], repetitions: 3 } });
        setEnvoi(false);
        onFait(slug, jouer);
    };

    const majMessage = (i: number, m: Message) => setHistorique((h) => h.map((x, k) => (k === i ? m : x)));

    return (
        <Dialog open onOpenChange={(o) => !o && onFermer()}>
            <DialogContent
                onOpenAutoFocus={(e) => e.preventDefault()}
                className="flex h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-4xl"
                data-testid="fenetre-de-test"
            >
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {test ? test.nom : t({ en: "New test", fr: "Nouveau test" })}
                        <Info>
                            {t({
                                en: "Personal data is replaced by fake data before the test is kept. The code judges the criteria; a required test that fails blocks the publication.",
                                fr: "Les données personnelles sont remplacées par des fausses avant d'enregistrer le test. Le code juge les critères ; un test obligatoire qui échoue bloque la publication.",
                            })}
                        </Info>
                    </DialogTitle>
                    {!test && (
                        <div className="mt-3 inline-flex rounded-lg bg-muted p-0.5 text-sm" role="group" aria-label={t({ en: "Kind of test", fr: "Sorte de test" })}>
                            {SORTES.map((s) => (
                                <button
                                    key={s.id}
                                    type="button"
                                    aria-pressed={sorte === s.id}
                                    title={t(s.info)}
                                    onClick={() => changerSorte(s.id)}
                                    className={`cursor-pointer rounded-md px-3 py-1 whitespace-nowrap ${sorte === s.id ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                >
                                    {t(s)}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto bg-background md:grid-cols-[18rem_1fr]">
                    <div className="space-y-4 border-b p-6 md:border-r md:border-b-0" data-testid="reglages-du-test">
                        <label className="block space-y-1 text-sm font-medium">
                            {t({ en: "Name", fr: "Nom" })}
                            <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Test name", fr: "Nom du test" })} />
                        </label>
                        <label className="block space-y-1 text-sm font-medium">
                            {t({ en: "Description", fr: "Description" })}
                            <Input value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
                        </label>
                        {sorte === "conversation" && (
                            <>
                                <div className="space-y-1 text-sm font-medium">
                                    <p className="flex items-center gap-1.5">
                                        {t({ en: "Caller character", fr: "Personnage d'appelant" })}
                                        <Info>{t({ en: "A character of the library; its behaviours are inside it.", fr: "Un personnage de la bibliothèque ; ses comportements sont dedans." })}</Info>
                                    </p>
                                    <Liste
                                        className="w-full"
                                        valeur={personnage}
                                        changer={setPersonnage}
                                        vide={t({ en: "No character", fr: "Aucun personnage" })}
                                        options={(ressources?.personnages ?? []).map((p) => ({ valeur: p.slug, libelle: p.titre }))}
                                    />
                                </div>
                                <label className="block space-y-1 text-sm font-medium">
                                    {t({ en: "First words", fr: "Premiers mots" })}
                                    <Input value={ouverture} onChange={(e) => setOuverture(e.target.value)} />
                                </label>
                                <label className="block space-y-1 text-sm font-medium">
                                    {t({ en: "Turns (2 to 40)", fr: "Tours (2 à 40)" })}
                                    <Input value={tours} inputMode="numeric" className="w-24" onChange={(e) => setTours(e.target.value.replace(/[^\d]/g, ""))} />
                                </label>
                                <label className="block space-y-1 text-sm font-medium">
                                    <span className="flex items-center gap-1.5">
                                        {t({ en: "Questions for the judge", fr: "Questions pour le juge" })}
                                        <Info>{t({ en: "One per line. The judge's opinion blocks nothing.", fr: "Une par ligne. L'avis du juge ne bloque rien." })}</Info>
                                    </span>
                                    <Textarea rows={3} value={questions} onChange={(e) => setQuestions(e.target.value)} />
                                </label>
                            </>
                        )}
                    </div>
                    <div className="space-y-5 p-6" data-testid="conversation-du-test-fenetre">
                        {sorte === "conversation" ? (
                            <label className="block space-y-1 text-sm font-medium">
                                {t({ en: "What the caller wants", fr: "Ce que l'appelant veut" })}
                                <Textarea rows={5} value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label={t({ en: "Scenario", fr: "Scénario" })} />
                            </label>
                        ) : (
                            <div className="space-y-2">
                                <p className="flex items-center gap-1.5 text-sm font-medium">
                                    {t({ en: "History before the reply", fr: "Historique avant la réplique" })}
                                    <Info>{t({ en: "The turns that came before; the agent answers after the reply below.", fr: "Les tours d'avant ; l'agent répond après la réplique ci-dessous." })}</Info>
                                </p>
                                {historique.map((m, i) => (
                                    <div key={i} className="flex items-center gap-2">
                                        <Liste
                                            className="w-32"
                                            valeur={m.role}
                                            changer={(v) => majMessage(i, { ...m, role: v as Message["role"] })}
                                            options={[
                                                { valeur: "assistant", libelle: t({ en: "Agent", fr: "Agent" }) },
                                                { valeur: "user", libelle: t({ en: "Caller", fr: "Appelant" }) },
                                            ]}
                                        />
                                        <Input className="flex-1" value={m.texte} aria-label={`${t({ en: "Turn", fr: "Tour" })} ${i + 1}`} onChange={(e) => majMessage(i, { ...m, texte: e.target.value })} />
                                        <Button variant="ghost" size="sm" onClick={() => setHistorique((h) => h.filter((_, k) => k !== i))}>
                                            {t({ en: "Remove", fr: "Retirer" })}
                                        </Button>
                                    </div>
                                ))}
                                <Button variant="outline" size="sm" onClick={() => setHistorique((h) => [...h, { role: h.length % 2 === 0 ? "assistant" : "user", texte: "" }])}>
                                    {t({ en: "Add a turn", fr: "Ajouter un tour" })}
                                </Button>
                                <label className="block space-y-1 pt-2 text-sm font-medium">
                                    {t({ en: "The caller's reply", fr: "La réplique de l'appelant" })}
                                    <Textarea rows={2} value={replique} onChange={(e) => setReplique(e.target.value)} aria-label={t({ en: "Reply", fr: "Réplique" })} />
                                </label>
                            </div>
                        )}
                        <div className="space-y-2">
                            <p className="flex items-center gap-1.5 text-sm font-medium">
                                {t({ en: "Criteria", fr: "Critères" })}
                                <Info>{t({ en: "Judged by the code, never by a model.", fr: "Jugés par le code, jamais par un modèle." })}</Info>
                            </p>
                            <EditeurDeCriteres lignes={criteres} changer={setCriteres} ressources={ressources} types={typesOfferts} />
                        </div>
                        {erreur && (
                            <p role="alert" className="text-sm text-destructive">
                                {erreur}
                            </p>
                        )}
                    </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-3 border-t px-6 py-3">
                    <label className="flex items-center gap-2 text-sm">
                        {t({ en: "Folder", fr: "Dossier" })}
                        <Input className="h-8 w-40" value={dossier} onChange={(e) => setDossier(e.target.value)} aria-label={t({ en: "Folder", fr: "Dossier" })} />
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                        <Switch checked={obligatoire} onCheckedChange={setObligatoire} aria-label={t({ en: "Required", fr: "Obligatoire" })} />
                        {t({ en: "Required", fr: "Obligatoire" })}
                        <Info>{t({ en: "A required test that fails blocks the publication.", fr: "Un test obligatoire qui échoue bloque la publication." })}</Info>
                    </label>
                    {test && onSupprimer && (
                        <Button variant="ghost" size="sm" onClick={onSupprimer}>
                            {t({ en: "Delete", fr: "Supprimer" })}
                        </Button>
                    )}
                    <div className="ml-auto flex gap-2">
                        <Button variant="outline" disabled={!pret || envoi} onClick={() => void envoyer(false)}>
                            {test ? t({ en: "Save", fr: "Enregistrer" }) : t({ en: "Create", fr: "Créer" })}
                        </Button>
                        <Button disabled={!pret || envoi} onClick={() => void envoyer(true)}>
                            {test ? t({ en: "Save and play", fr: "Enregistrer et jouer" }) : t({ en: "Create and play", fr: "Créer et jouer" })}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
