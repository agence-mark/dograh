"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A11, 1A et 1C du plan du 13/10) : la brique « Agent »
 * sous une étape.
 *
 * Une étape peut passer l'appel à un autre agent de l'organisation. La brique en est l'écran : une
 * modale CENTRÉE « Choisir un agent » (les agents du groupe d'abord, puis les autres de
 * l'organisation, l'agent courant exclu), la phrase d'annonce, « l'agent choisi dit son accueil :
 * oui / non ». Elle crée l'outil ``transfer_agent`` (un outil, une destination) et le rattache à
 * l'étape ; un clic sur une brique réglée ouvre l'agent cible dans un nouvel onglet.
 *
 * ⛔ AFFICHAGE PUR : le graphe ne change pas de comportement. Ce que la brique écrit, c'est un outil
 * et son uuid dans ``tool_uuids`` de l'étape, exactement ce que l'écran des outils produisait déjà ;
 * le moteur lit les mêmes outils qu'avant. La fenêtre d'une étape n'est jamais traduite (T3), mais
 * ce composant est le nôtre : ses textes sont dans les deux langues.
 */
import { ExternalLink, Plus, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useWorkflow } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import {
    createToolApiV1ToolsPost,
    getWorkflowsApiV1WorkflowFetchGet,
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet,
} from "@/client/sdk.gen";
import type { ToolResponse, WorkflowListResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

const TEXTES = {
    titre: { en: "Agents", fr: "Agents" },
    aide: {
        en: "Hands the call to another agent of the organization. One brick, one destination: the model chooses between the bricks of the step by their names and descriptions.",
        fr: "Passe l'appel à un autre agent de l'organisation. Une brique, une destination : le modèle choisit entre les briques de l'étape d'après leurs noms et leurs descriptions.",
    },
    aucune: { en: "No agent on this step.", fr: "Aucun agent sur cette étape." },
    ajouter: { en: "Add an agent", fr: "Ajouter un agent" },
    retirer: { en: "Detach this agent from the step", fr: "Détacher cet agent de l'étape" },
    ouvrir: { en: "Open the agent in a new tab", fr: "Ouvrir l'agent dans un nouvel onglet" },
    modaleTitre: { en: "Choose an agent", fr: "Choisir un agent" },
    modaleDescription: {
        en: "The call goes to the agent you choose when this step decides to hand it over.",
        fr: "L'appel passe à l'agent choisi quand cette étape décide de le lui passer.",
    },
    duGroupe: { en: "Agents of the group", fr: "Agents du groupe" },
    autres: { en: "Other agents of the organization", fr: "Autres agents de l'organisation" },
    aucunAgent: { en: "No other agent in the organization.", fr: "Aucun autre agent dans l'organisation." },
    annonce: { en: "Announcement sentence", fr: "Phrase d'annonce" },
    annonceAide: {
        en: "Said by this agent, with the call's voice, before the call is handed over. Empty: no announcement.",
        fr: "Dite par cet agent, avec la voix de l'appel, avant de passer l'appel. Vide : aucune annonce.",
    },
    accueil: { en: "The chosen agent says its greeting", fr: "L'agent choisi dit son accueil" },
    accueilOui: { en: "yes", fr: "oui" },
    accueilNon: { en: "no", fr: "non" },
    accueilAide: {
        en: "No: it opens with a reply that continues the conversation instead of introducing itself again.",
        fr: "Non : il ouvre par une réplique qui poursuit la conversation au lieu de se présenter de nouveau.",
    },
    annuler: { en: "Cancel", fr: "Annuler" },
    valider: { en: "Add the agent", fr: "Ajouter l'agent" },
    enCours: { en: "Adding...", fr: "Ajout..." },
    echec: { en: "The agent could not be added.", fr: "L'agent n'a pas pu être ajouté." },
    inconnu: { en: "Unknown agent", fr: "Agent inconnu" },
    sansAnnonce: { en: "no announcement", fr: "sans annonce" },
} satisfies Record<string, Texte>;

interface ConfigPassation {
    workflow_id?: number;
    message?: string;
    play_greeting?: boolean;
}

const configDe = (outil: ToolResponse): ConfigPassation =>
    ((outil.definition as { config?: ConfigPassation } | undefined)?.config ?? {}) as ConfigPassation;

/** L'outil de passation à propos d'un agent : nom et description que le modèle lit pour choisir. */
export const outilDePassation = (
    cible: { id: number; name: string },
    annonce: string,
    accueil: boolean,
    dejaPris: string[],
) => {
    const fonction = (nom: string) => nom.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
    const base = `Passer à ${cible.name}`;
    let nom = base;
    for (let n = 2; dejaPris.includes(fonction(nom)) || fonction(nom) === ""; n += 1) nom = `${base} ${n}`;
    return {
        name: nom,
        description: `Passe l'appel à l'agent « ${cible.name} ». À utiliser quand la demande de l'appelant relève de cet agent : décris ici dans quel cas.`,
        category: "transfer_agent" as const,
        definition: {
            schema_version: 1,
            type: "transfer_agent" as const,
            config: { workflow_id: cible.id, message: annonce.trim(), play_greeting: accueil },
        },
    };
};

export const BriqueAgent = ({
    outilsUuids,
    onChange,
}: {
    /** Les outils de l'étape (``tool_uuids``). */
    outilsUuids: string[];
    onChange: (uuids: string[]) => void;
}) => {
    const { t } = useLangue();
    const { tools, workflowId, ajouterOutil } = useWorkflow();
    const [agents, setAgents] = useState<WorkflowListResponse[]>([]);
    const [dansLeGroupe, setDansLeGroupe] = useState<Set<number>>(new Set());
    const [ouverte, setOuverte] = useState(false);
    const [choisi, setChoisi] = useState<number | null>(null);
    const [annonce, setAnnonce] = useState("");
    const [accueil, setAccueil] = useState(false);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        let annule = false;
        (async () => {
            try {
                const [liste, groupe] = await Promise.all([
                    getWorkflowsApiV1WorkflowFetchGet({ query: { status: "active" } }),
                    workflowId !== undefined
                        ? lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet({ path: { workflow_id: workflowId } })
                        : Promise.resolve(undefined),
                ]);
                if (annule) return;
                const donnees = liste?.data;
                setAgents(Array.isArray(donnees) ? donnees : []);
                const g = groupe?.data;
                const ids = new Set<number>();
                if (g?.principal) ids.add(g.principal.id);
                for (const m of g?.specialises ?? []) ids.add(m.id);
                setDansLeGroupe(ids);
            } catch {
                // Sans la liste : les briques s'affichent sans le nom de l'agent, la modale reste vide.
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId]);

    const passations = useMemo(
        () => (tools ?? []).filter((o) => outilsUuids.includes(o.tool_uuid) && o.category === "transfer_agent"),
        [tools, outilsUuids],
    );
    const nomDe = (id: number | undefined) => agents.find((a) => a.id === id)?.name;

    const candidats = agents.filter((a) => a.id !== workflowId);
    const duGroupe = candidats.filter((a) => dansLeGroupe.has(a.id));
    const autres = candidats.filter((a) => !dansLeGroupe.has(a.id));

    const ouvrir = () => {
        setChoisi(null);
        setAnnonce("");
        setAccueil(false);
        setOuverte(true);
    };

    const valider = async () => {
        const cible = agents.find((a) => a.id === choisi);
        if (!cible) return;
        setEnCours(true);
        try {
            const dejaPris = (tools ?? [])
                .filter((o) => outilsUuids.includes(o.tool_uuid))
                .map((o) => o.name.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, ""));
            const reponse = await createToolApiV1ToolsPost({
                body: outilDePassation(cible, annonce, accueil, dejaPris),
            });
            if (reponse.error || !reponse.data) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echec)));
                return;
            }
            ajouterOutil?.(reponse.data);
            onChange([...outilsUuids, reponse.data.tool_uuid]);
            setOuverte(false);
        } catch {
            toast.error(t(TEXTES.echec));
        } finally {
            setEnCours(false);
        }
    };

    const Choix = ({ liste }: { liste: WorkflowListResponse[] }) => (
        <ul className="space-y-1">
            {liste.map((a) => (
                <li key={a.id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-accent">
                        <input type="radio" name="brique-agent-cible" checked={choisi === a.id} onChange={() => setChoisi(a.id)} />
                        <UserRound className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                        {a.name}
                    </label>
                </li>
            ))}
        </ul>
    );

    return (
        <div className="grid gap-2" data-brique="agent">
            <div>
                <p className="text-sm font-medium">{t(TEXTES.titre)}</p>
                <p className="text-xs text-muted-foreground">{t(TEXTES.aide)}</p>
            </div>
            {passations.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t(TEXTES.aucune)}</p>
            ) : (
                <ul className="space-y-1" data-liste="briques-agent">
                    {passations.map((outil) => {
                        const config = configDe(outil);
                        const cible = config.workflow_id;
                        return (
                            <li key={outil.tool_uuid} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm" data-brique-agent={cible}>
                                <Link
                                    href={`/workflow/${cible}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    aria-label={t(TEXTES.ouvrir)}
                                    className="inline-flex min-w-0 flex-1 items-center gap-1 underline"
                                >
                                    <span className="truncate">{nomDe(cible) ?? t(TEXTES.inconnu)}</span>
                                    <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                                </Link>
                                <span className="shrink-0 text-xs text-muted-foreground">
                                    {config.message ? `« ${config.message} »` : t(TEXTES.sansAnnonce)}
                                    {" · "}
                                    {t(TEXTES.accueil)} : {config.play_greeting ? t(TEXTES.accueilOui) : t(TEXTES.accueilNon)}
                                </span>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 shrink-0"
                                    aria-label={t(TEXTES.retirer)}
                                    onClick={() => onChange(outilsUuids.filter((u) => u !== outil.tool_uuid))}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </li>
                        );
                    })}
                </ul>
            )}
            <div>
                <Button type="button" variant="outline" size="sm" onClick={ouvrir}>
                    <Plus className="mr-2 h-3.5 w-3.5" />
                    {t(TEXTES.ajouter)}
                </Button>
            </div>

            <Dialog open={ouverte} onOpenChange={setOuverte}>
                <DialogContent className="sm:max-w-lg" data-modale="choisir-un-agent">
                    <DialogHeader>
                        <DialogTitle>{t(TEXTES.modaleTitre)}</DialogTitle>
                        <DialogDescription>{t(TEXTES.modaleDescription)}</DialogDescription>
                    </DialogHeader>
                    <div className="max-h-[60vh] space-y-4 overflow-y-auto py-1">
                        {candidats.length === 0 && <p className="text-sm text-muted-foreground">{t(TEXTES.aucunAgent)}</p>}
                        {duGroupe.length > 0 && (
                            <div className="space-y-1" data-agents="du-groupe">
                                <p className="text-xs font-semibold">{t(TEXTES.duGroupe)}</p>
                                <Choix liste={duGroupe} />
                            </div>
                        )}
                        {autres.length > 0 && (
                            <div className="space-y-1" data-agents="autres">
                                <p className="text-xs font-semibold">{t(TEXTES.autres)}</p>
                                <Choix liste={autres} />
                            </div>
                        )}
                        <div className="space-y-1">
                            <Label htmlFor="brique-agent-annonce" className="text-xs">
                                {t(TEXTES.annonce)}
                            </Label>
                            <Input id="brique-agent-annonce" maxLength={500} value={annonce} onChange={(e) => setAnnonce(e.target.value)} />
                            <p className="text-xs text-muted-foreground">{t(TEXTES.annonceAide)}</p>
                        </div>
                        <div className="space-y-1">
                            <div className="flex items-center justify-between gap-3">
                                <Label htmlFor="brique-agent-accueil" className="text-sm">
                                    {t(TEXTES.accueil)}
                                </Label>
                                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                    {accueil ? t(TEXTES.accueilOui) : t(TEXTES.accueilNon)}
                                    <Switch id="brique-agent-accueil" checked={accueil} onCheckedChange={setAccueil} />
                                </span>
                            </div>
                            <p className="text-xs text-muted-foreground">{t(TEXTES.accueilAide)}</p>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setOuverte(false)}>
                            {t(TEXTES.annuler)}
                        </Button>
                        <Button type="button" onClick={valider} disabled={choisi === null || enCours}>
                            {enCours ? t(TEXTES.enCours) : t(TEXTES.valider)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};
