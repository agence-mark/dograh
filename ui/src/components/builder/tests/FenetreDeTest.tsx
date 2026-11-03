"use client";

/**
 * [.mark] U3 (E47): the window of a test, three kinds: a simulated conversation, the next reply, a tool call. Same shape as the
 * mockup (`tests-agent.tsx`, `EditeurTest`): the kinds as tabs over a left column (name, scenario, character, criteria, questions
 * for the judge), the conversation on the right, a fixed foot (delete with its confirmation, folder, required, cancel, create,
 * create and play). Creating and changing go through the same server function as the builder's actions. Every list (steps,
 * tools, outcomes, characters, folders) is read from the agent and the library; nothing is written in the screen.
 *
 * The « Environment » part of the mockup (simulated date, caller number, tool answers in series) is U11 and not built: it is not
 * drawn (`14-ecarts-maquette.md`).
 */
import { useBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { Bot, FolderPlus, Play, Plus, Trash2, User, X } from "lucide-react";
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

const Champ = ({ titre, info, children }: { titre: string; info?: string; children: React.ReactNode }) => (
    <div className="space-y-1.5">
        <p className="flex items-center gap-1.5 text-sm font-medium">
            {titre}
            {info && <Info>{info}</Info>}
        </p>
        {children}
    </div>
);

const Bulle = ({ role, texte }: Message) => (
    <div className={`flex gap-2 ${role === "user" ? "flex-row-reverse" : ""}`}>
        <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border bg-background">
            {role === "assistant" ? <Bot className="size-3.5" /> : <User className="size-3.5" />}
        </span>
        <p className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${role === "user" ? "bg-foreground text-background" : "border bg-background"}`}>{texte}</p>
    </div>
);

export function FenetreDeTest({
    workflowId,
    test,
    ressources,
    onFermer,
    onFait,
    onSupprimer,
    dossiers = [],
    derniere = null,
}: {
    workflowId: number;
    test?: TestComplet;
    ressources: RessourcesDeTest | null;
    onFermer: () => void;
    /** `slug` of the test written; `jouer` when « and play » was chosen. */
    onFait: (slug: string, jouer: boolean) => void;
    onSupprimer?: () => void;
    /** The folders the agent's tests already use (the foot's list). */
    dossiers?: string[];
    /** The last result of the open test, said on the right of a simulated conversation. */
    derniere?: { le: string; reussis: number; total: number } | null;
}) {
    const { t, langue } = useLangue();
    // K6 : tant que la fenêtre est ouverte, une modification de l'agent ailleurs ne la ferme pas (la saisie serait perdue).
    useBrouillonLocal(true);
    const [sorte, setSorte] = useState<SorteDeTest>(test ? sorteDuTest(test) : "conversation");
    const [nom, setNom] = useState(test?.nom ?? "");
    const [description, setDescription] = useState(test?.description ?? "");
    const [dossier, setDossier] = useState(test?.dossier ?? "");
    const [obligatoire, setObligatoire] = useState(test?.obligatoire ?? false);
    const [criteres, setCriteres] = useState<LigneDeCritere[]>(test ? test.criteres.map(ligneDuCritere) : [ligneVide()]);
    // The mockup shows ONE conversation: the history, then the replayed reply (the caller's last line).
    const [fil, setFil] = useState<Message[]>(() => [
        ...((test?.historique ?? []) as Message[]).map((m): Message => ({ role: m.role === "assistant" ? "assistant" : "user", texte: m.texte })),
        { role: "user", texte: test?.replique ?? "" },
    ]);
    const [scenario, setScenario] = useState(test?.scenario?.but ?? "");
    const [personnage, setPersonnage] = useState(test?.scenario?.personnage ?? "");
    const [ouverture, setOuverture] = useState(test?.scenario?.ouverture ?? "");
    const [tours, setTours] = useState(test?.scenario?.tours_max ? String(test.scenario.tours_max) : "");
    const [questions, setQuestions] = useState<string[]>((test as { questions_juge?: string[] } | undefined)?.questions_juge ?? []);
    const [erreur, setErreur] = useState<string | null>(null);
    const [envoi, setEnvoi] = useState(false);
    const [aSupprimer, setASupprimer] = useState(false);
    const [nouveauDossier, setNouveauDossier] = useState(false);

    const derniereLigne = fil[fil.length - 1];
    const replique = derniereLigne?.role === "user" ? derniereLigne.texte : "";
    const historique = fil.slice(0, -1);

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
            questions_juge: questions.map((q) => q.trim()).filter(Boolean),
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

    const majMessage = (i: number, m: Message) => setFil((h) => h.map((x, k) => (k === i ? m : x)));
    const ajouterAvant = (role: Message["role"]) => setFil((h) => [...h.slice(0, -1), { role, texte: "" }, h[h.length - 1]]);
    const listeDossiers = [...new Set([...dossiers, ...(dossier ? [dossier] : [])])].filter(Boolean);
    const date = (iso: string) => new Date(iso).toLocaleDateString(langue === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit" });

    return (
        <Dialog open onOpenChange={(o) => !o && onFermer()}>
            <DialogContent
                onOpenAutoFocus={(e) => e.preventDefault()}
                className="flex h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl"
                data-testid="fenetre-de-test"
            >
                <DialogTitle className="sr-only">{test ? test.nom : t({ en: "New test", fr: "Nouveau test" })}</DialogTitle>
                <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[440px_1fr]">
                    <div className="flex min-h-0 flex-col border-r">
                        <div className="grid shrink-0 grid-cols-3 border-b text-sm" role="group" aria-label={t({ en: "Kind of test", fr: "Sorte de test" })}>
                            {SORTES.map((s) => (
                                <button
                                    key={s.id}
                                    type="button"
                                    aria-pressed={sorte === s.id}
                                    title={t(s.info)}
                                    disabled={!!test && sorteDuTest(test) !== s.id}
                                    onClick={() => changerSorte(s.id)}
                                    className={`-mb-px cursor-pointer border-b-2 py-3 hover:font-medium disabled:cursor-default disabled:opacity-40 ${sorte === s.id ? "border-foreground font-medium" : "border-transparent text-muted-foreground"}`}
                                >
                                    {t(s)}
                                </button>
                            ))}
                        </div>
                        <div className="min-h-0 flex-1 space-y-5 overflow-auto p-5" data-testid="reglages-du-test">
                            <Champ titre={t({ en: "Test name", fr: "Nom du test" })}>
                                <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Test name", fr: "Nom du test" })} />
                            </Champ>
                            <Champ titre="Description">
                                <Input value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
                            </Champ>
                            {sorte === "conversation" && (
                                <>
                                    <Champ
                                        titre={t({ en: "Scenario", fr: "Scénario" })}
                                        info={t({ en: "What the simulated caller wants, what they know and what they do not.", fr: "Ce que veut l'appelant simulé, ce qu'il sait et ce qu'il ignore." })}
                                    >
                                        <Textarea rows={4} value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label={t({ en: "Scenario", fr: "Scénario" })} />
                                    </Champ>
                                    <Champ
                                        titre={t({ en: "Character", fr: "Personnage" })}
                                        info={t({ en: "Read from the library: its description and its behaviours enter the simulated caller's instruction.", fr: "Lu dans la bibliothèque : sa description et ses comportements entrent dans la consigne de l'appelant simulé." })}
                                    >
                                        <Liste
                                            className="w-full"
                                            valeur={personnage}
                                            changer={setPersonnage}
                                            vide={t({ en: "No character", fr: "Aucun personnage" })}
                                            options={(ressources?.personnages ?? []).map((p) => ({ valeur: p.slug, libelle: p.titre }))}
                                        />
                                    </Champ>
                                    <Champ
                                        titre={t({ en: "Caller's first words", fr: "Premiers mots de l'appelant" })}
                                        info={t({ en: "Optional. Empty: the simulated caller opens by itself, following the scenario.", fr: "Facultatif. Vide : l'appelant simulé ouvre lui-même selon le scénario." })}
                                    >
                                        <Input value={ouverture} onChange={(e) => setOuverture(e.target.value)} />
                                    </Champ>
                                    <Champ
                                        titre={t({ en: "Maximum turns", fr: "Tours maximum" })}
                                        info={t({ en: "Between 2 and 40. The call stops earlier if the agent or the caller concludes.", fr: "Entre 2 et 40. L'appel s'arrête avant si l'agent ou l'appelant conclut." })}
                                    >
                                        <Input value={tours} inputMode="numeric" className="w-24" onChange={(e) => setTours(e.target.value.replace(/[^\d]/g, ""))} />
                                    </Champ>
                                </>
                            )}
                            <Champ
                                titre={sorte === "outil" ? t({ en: "Expected tool", fr: "Outil attendu" }) : t({ en: "Success criteria", fr: "Critères de réussite" })}
                                info={t({ en: "Judged by the code on what happened, never by a model. 12 at most.", fr: "Vérifiés par le code sur ce qui s'est passé, jamais par un modèle. 12 au plus." })}
                            >
                                <EditeurDeCriteres lignes={criteres} changer={setCriteres} ressources={ressources} types={typesOfferts} />
                            </Champ>
                            {sorte === "conversation" && (
                                <Champ
                                    titre={t({ en: "Questions for the judge", fr: "Questions au juge" })}
                                    info={t({ en: "Not blocking: the judge answers yes or no with its reason, next to the code's verdict. They never make the test fail.", fr: "Non bloquantes : le juge répond oui ou non avec sa raison, à côté du verdict du code. Elles ne font jamais échouer le test." })}
                                >
                                    <div className="space-y-2">
                                        {questions.map((q, i) => (
                                            <div key={i} className="flex gap-2">
                                                <Input
                                                    value={q}
                                                    className="h-8"
                                                    aria-label={`${t({ en: "Question", fr: "Question" })} ${i + 1}`}
                                                    onChange={(e) => setQuestions((l) => l.map((x, j) => (j === i ? e.target.value : x)))}
                                                />
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    aria-label={t({ en: "Remove the question", fr: "Retirer la question" })}
                                                    onClick={() => setQuestions((l) => l.filter((_, j) => j !== i))}
                                                >
                                                    <X className="size-4" />
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                    <Button variant="outline" size="sm" className="mt-2" onClick={() => setQuestions((l) => [...l, ""])}>
                                        <Plus className="size-3.5" /> {t({ en: "Add a question", fr: "Ajouter une question" })}
                                    </Button>
                                </Champ>
                            )}
                            {erreur && (
                                <p role="alert" className="text-sm text-destructive">
                                    {erreur}
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="flex min-h-0 flex-col" data-testid="conversation-du-test-fenetre">
                        {sorte === "conversation" ? (
                            <div className="flex-1 space-y-3 overflow-auto p-6">
                                {ouverture.trim() && <Bulle role="user" texte={ouverture} />}
                                {derniere ? (
                                    <div className="space-y-1 border-t pt-4 text-sm">
                                        <p className="font-medium">
                                            {t({ en: "Last attempt", fr: "Dernier essai" })} · {date(derniere.le)} · {derniere.reussis}/{derniere.total}
                                        </p>
                                    </div>
                                ) : (
                                    <p className="flex items-center justify-center gap-1.5 pt-10 text-center text-sm text-muted-foreground">
                                        {t({ en: "Not played yet", fr: "Pas encore joué" })}
                                        <Info>
                                            {t({
                                                en: "The simulated caller goes on with the conversation following the scenario and the character; the whole conversation is checked by the criteria and shown here.",
                                                fr: "L'appelant simulé poursuit la conversation selon le scénario et le personnage ; la conversation entière est vérifiée par les critères et visible ici.",
                                            })}
                                        </Info>
                                    </p>
                                )}
                            </div>
                        ) : (
                            <div className="flex-1 space-y-3 overflow-auto p-6">
                                <p className="flex items-center gap-1.5 text-sm font-medium">
                                    {t({ en: "History before the reply", fr: "Historique avant la réplique" })}
                                    <Info>{t({ en: "The turns that came before; the agent answers after the caller's last line, which is replayed.", fr: "Les tours d'avant ; l'agent répond après la dernière ligne de l'appelant, qui est rejouée." })}</Info>
                                </p>
                                {fil.map((m, i) => {
                                    const derniereDuFil = i === fil.length - 1;
                                    return (
                                        <div key={i} className={`group flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                                            <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border bg-background">
                                                {m.role === "assistant" ? <Bot className="size-3.5" /> : <User className="size-3.5" />}
                                            </span>
                                            <div className="max-w-[75%] space-y-1">
                                                <Textarea
                                                    rows={1}
                                                    value={m.texte}
                                                    aria-label={derniereDuFil ? t({ en: "Reply", fr: "Réplique" }) : `${t({ en: "Turn", fr: "Tour" })} ${i + 1}`}
                                                    placeholder={derniereDuFil ? t({ en: "The replayed reply", fr: "La réplique rejouée" }) : ""}
                                                    onChange={(e) => majMessage(i, { ...m, texte: e.target.value })}
                                                    className={`min-h-0 resize-none text-sm ${m.role === "user" ? "bg-foreground text-background placeholder:text-background/50" : "bg-background"}`}
                                                />
                                                {derniereDuFil && (
                                                    <p className="text-right text-[11px] text-muted-foreground">
                                                        {t({ en: "replayed: the agent's answer is checked", fr: "rejouée : la réponse de l'agent est vérifiée" })}
                                                    </p>
                                                )}
                                            </div>
                                            {!derniereDuFil && (
                                                <button
                                                    type="button"
                                                    aria-label={t({ en: "Remove the turn", fr: "Retirer le tour" })}
                                                    onClick={() => setFil((h) => h.filter((_, k) => k !== i))}
                                                    className="cursor-pointer text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                                                >
                                                    <X className="size-3.5" />
                                                </button>
                                            )}
                                        </div>
                                    );
                                })}
                                <div className="flex gap-2 pt-2">
                                    <Button variant="outline" size="sm" onClick={() => ajouterAvant("assistant")}>
                                        <Bot className="size-3.5" /> {t({ en: "Agent turn", fr: "Réplique de l'agent" })}
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={() => ajouterAvant("user")}>
                                        <User className="size-3.5" /> {t({ en: "Caller turn", fr: "Réplique de l'appelant" })}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-3 border-t px-5 py-3">
                    {test &&
                        onSupprimer &&
                        (aSupprimer ? (
                            <>
                                <span className="text-sm">{t({ en: "Delete this test and its results?", fr: "Supprimer ce test et ses résultats ?" })}</span>
                                <Button variant="outline" size="sm" onClick={() => setASupprimer(false)}>
                                    {t({ en: "No", fr: "Non" })}
                                </Button>
                                <Button size="sm" variant="destructive" onClick={onSupprimer}>
                                    {t({ en: "Delete", fr: "Supprimer" })}
                                </Button>
                            </>
                        ) : (
                            <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => setASupprimer(true)}>
                                <Trash2 className="size-4" /> {t({ en: "Delete", fr: "Supprimer" })}
                            </Button>
                        ))}
                    <span className="flex items-center gap-2 text-sm">
                        <FolderPlus className="size-4 text-muted-foreground" />
                        {nouveauDossier ? (
                            <Input
                                autoFocus
                                value={dossier}
                                onChange={(e) => setDossier(e.target.value)}
                                onBlur={() => setNouveauDossier(false)}
                                placeholder={t({ en: "Folder name", fr: "Nom du dossier" })}
                                aria-label={t({ en: "Folder", fr: "Dossier" })}
                                className="h-8 w-40"
                            />
                        ) : (
                            <Liste
                                valeur={dossier}
                                changer={(v) => {
                                    if (v === "+") {
                                        setDossier("");
                                        setNouveauDossier(true);
                                    } else setDossier(v);
                                }}
                                vide={t({ en: "No folder", fr: "Sans dossier" })}
                                options={[...listeDossiers.map((d) => ({ valeur: d, libelle: d })), { valeur: "+", libelle: t({ en: "New folder…", fr: "Nouveau dossier…" }) }]}
                            />
                        )}
                    </span>
                    <label className="flex items-center gap-2 text-sm">
                        <Switch checked={obligatoire} onCheckedChange={setObligatoire} aria-label={t({ en: "Required", fr: "Obligatoire" })} />
                        {t({ en: "Required", fr: "Obligatoire" })}
                        <Info>{t({ en: "A required test that fails blocks the publication of the agent.", fr: "Un test obligatoire qui échoue bloque la publication de l'agent." })}</Info>
                    </label>
                    <span className="flex-1" />
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button variant="outline" disabled={!pret || envoi} onClick={() => void envoyer(false)}>
                        {test ? t({ en: "Save", fr: "Enregistrer" }) : t({ en: "Create", fr: "Créer" })}
                    </Button>
                    <Button disabled={!pret || envoi} onClick={() => void envoyer(true)}>
                        <Play className="size-4" /> {test ? t({ en: "Save and play", fr: "Enregistrer et jouer" }) : t({ en: "Create and play", fr: "Créer et jouer" })}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
