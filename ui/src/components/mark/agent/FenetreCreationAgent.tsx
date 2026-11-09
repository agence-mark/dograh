"use client";

/**
 * [.mark] Partie 3, sous-lot 9 (audit du 04/11, 04 § 1 « Création », 16) : la fenêtre de création d'agent UNIQUE, reprise de la
 * maquette (`liste-agents.tsx`, `ModaleNouvelAgent`). Elle remplace les deux fenêtres d'avant (`ModaleNouvelAgent`,
 * `ModaleCreationAgent`) : le bouton « Nouvel agent » de la liste et l'étape 6 de « Nouveau client » ouvrent celle-ci.
 *
 * - Structure : un groupe avec spécialistes, ou un agent (le groupe est grisé en temps réel : il change de modèle d'un agent à
 *   l'autre, ce qu'une session temps réel ne peut pas faire) ;
 * - Recette : AUCUN choix à la création (Evan, 09/11) : elle vit dans la bibliothèque, le serveur pose celle par défaut (réglable) et
 *   c'est le builder qui l'applique en posant ses questions ;
 * - Cerveau : en chaîne (défaut) ou temps réel (posé sur l'agent créé, `model_overrides.is_realtime`) ; en temps réel, la liste
 *   des fonctions qui ne jouent qu'en chaîne est montrée grisée ;
 * - Point de départ : avec le builder (panneau ouvert), depuis une recette (la recette posée, sans le builder), vide (gabarit neutre).
 *
 * Centrée (règle d'Evan : « Nouvel agent » et les créations de ce type). Chaque chemin appelle la route de création qui existe
 * (`POST /workflow/groupe`, `POST /workflow/create/template`). Avec `organisationId`, toutes ses requêtes vont à ce client (en-tête
 * d'organisation, contrôlé par le serveur) ; avec `surCree`, rien n'est ouvert : l'appelant reçoit l'agent créé.
 */
import { FileText, Plus, Sparkles, Users2, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
    createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost,
    creerUnGroupeApiV1WorkflowGroupePost,
    updateWorkflowApiV1WorkflowWorkflowIdPut,
} from "@/client/sdk.gen";
import type { WorkflowConfigurationDefaults } from "@/client/types.gen";
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ENTETE_ORGANISATION } from "@/lib/espaceCourant";

import { adresseOnglet } from "./onglets-agent";

const T = {
    titre: { en: "New agent", fr: "Nouvel agent" },
    info: {
        en: "Created as a draft. This is the only creation window: the agents list button and a client's setup open this one.",
        fr: "Créé en brouillon. C'est la seule fenêtre de création : le bouton de la liste des agents et l'installation d'un client ouvrent celle-ci.",
    },
    resume: { en: "Structure, recipe, brain and starting point of the new agent.", fr: "Structure, recette, cerveau et point de départ du nouvel agent." },
    nom: { en: "Name", fr: "Nom" },
    nomRequis: { en: "Give the agent a name.", fr: "Donnez un nom à l'agent." },
    structure: { en: "Structure", fr: "Structure" },
    structureInfo: {
        en: "A group always has a main agent and specialists; each specialist has a single « Return » section.",
        fr: "Un groupe a toujours un agent principal et des spécialistes ; chaque spécialiste a une section « Retour » unique.",
    },
    groupe: { en: "Group with specialists", fr: "Groupe avec spécialistes" },
    groupePhrase: { en: "A greeter and one specialist per call reason.", fr: "Un accueil, un spécialiste par motif d'appel." },
    groupeBloque: {
        en: "A group hands the call from one agent to another: impossible in real time. Switch the brain back to chain to pick it.",
        fr: "Un groupe passe l'appel d'un agent à l'autre : impossible en temps réel. Repasser le cerveau en chaîne pour le choisir.",
    },
    un: { en: "One agent", fr: "Un agent" },
    unPhrase: { en: "One prompt and a few steps. For a simple need or the site.", fr: "Un seul prompt et peu d'étapes. Pour un besoin simple ou le site." },
    cerveau: { en: "Brain", fr: "Cerveau" },
    cerveauInfo: {
        en: "Chain: transcription, model and voice are three services you set, and the whole agent engine plays. Real time: one model listens and speaks, faster to answer, but without the chain features below.",
        fr: "En chaîne : la transcription, le modèle et la voix sont trois services réglables, et tout le moteur de l'agent joue. En temps réel : un seul modèle écoute et parle, plus rapide à répondre, mais sans les fonctions de chaîne ci-dessous.",
    },
    chaine: { en: "Chain", fr: "En chaîne" },
    chainePhrase: { en: "Transcription, model, voice: three services you set.", fr: "Transcription, modèle, voix : trois services réglables." },
    tempsReel: { en: "Real time", fr: "Temps réel" },
    tempsReelPhrase: { en: "One model listens and speaks.", fr: "Un seul modèle écoute et parle." },
    chaineSeulement: { en: "Only works in chain", fr: "Ne fonctionne qu'en chaîne" },
    chaineSeulementInfo: {
        en: "These features are greyed out: they rely on separate transcription and model. Switching the brain to chain makes them available.",
        fr: "Ces fonctions sont grisées : elles reposent sur la transcription et le modèle séparés. Passer le cerveau en chaîne les rend disponibles.",
    },
    depart: { en: "Starting point", fr: "Point de départ" },
    builder: { en: "With the builder", fr: "Avec le builder" },
    builderPhrase: { en: "It reads the files, asks its questions, writes the design.", fr: "Il lit les dossiers, pose ses questions, rédige la conception." },
    recette: { en: "From a recipe", fr: "Depuis une recette" },
    recettePhrase: { en: "A structure from the library, to fill in.", fr: "Une structure de la bibliothèque, à remplir." },
    vide: { en: "Empty", fr: "Vide" },
    videPhrase: { en: "Empty graph, Start then End.", fr: "Graphe vierge, Départ puis Fin." },
    description: { en: "What the company does and what the agent must do, in a few lines.", fr: "Ce que fait l'entreprise et ce que l'agent doit faire, en quelques lignes." },
    annuler: { en: "Cancel", fr: "Annuler" },
    lancer: { en: "Start the builder", fr: "Lancer le builder" },
    creer: { en: "Create the draft", fr: "Créer le brouillon" },
    enCours: { en: "Creating...", fr: "Création..." },
    cree: { en: "Agent created as a draft.", fr: "Agent créé en brouillon." },
    echec: { en: "Agent not created. Try again.", fr: "Agent non créé. Réessayez." },
    tempsReelNonPose: {
        en: "Agent created, but the real-time brain was not set. Set it in Settings › Models.",
        fr: "Agent créé, mais le cerveau temps réel n'a pas été posé. Réglez-le dans Réglages › Modèles.",
    },
} satisfies Record<string, Texte>;

/** Les fonctions du moteur qui ne jouent qu'en chaîne (maquette, `CHAINE_SEULEMENT`). */
const CHAINE_SEULEMENT: { nom: Texte; info: Texte }[] = [
    {
        nom: { en: "Call record", fr: "Fiche de l'appel" },
        info: {
            en: "The record fills during the call through a small model or a tool, between transcription and voice. In real time one model listens and speaks: there is no place for the record to fill.",
            fr: "La fiche se remplit pendant l'appel grâce à un petit modèle ou à un outil, entre la transcription et la voix. En temps réel, un seul modèle écoute et parle : il n'y a pas d'endroit où la fiche puisse se remplir.",
        },
    },
    {
        nom: { en: "Clerk", fr: "Greffier" },
        info: {
            en: "The clerk is a separate model that notes what the caller says. It reads the transcript turn by turn, which real time does not produce.",
            fr: "Le greffier est un modèle séparé qui note ce que dit l'appelant. Il lit la transcription tour par tour, ce que le temps réel ne produit pas.",
        },
    },
    {
        nom: { en: "Gates written in the answer", fr: "Portes écrites dans la réponse" },
        info: {
            en: "The code reads the end of the model's answer to take the gate. In real time the answer goes straight to the voice: there is nothing for the code to read.",
            fr: "Le code lit la fin de la réponse du modèle pour prendre la porte. En temps réel, la réponse part directement à la voix : le code n'a rien à lire.",
        },
    },
    {
        nom: { en: "Step change by the record", fr: "Changement d'étape par la fiche" },
        info: {
            en: "The code reads the record at the end of each answer to move from one step to another. Without a record this mode cannot play.",
            fr: "Le code lit la fiche à chaque fin de réponse pour passer d'une étape à l'autre. Sans fiche, ce mode ne peut pas jouer.",
        },
    },
    {
        nom: { en: "Arbiter", fr: "Arbitre" },
        info: {
            en: "A small separate model decides the move before the agent answers. In real time the answer starts too fast to wait for it.",
            fr: "Un petit modèle séparé tranche le passage avant que l'agent réponde. En temps réel, la réponse commence trop vite pour l'attendre.",
        },
    },
    {
        nom: { en: "Specialists", fr: "Spécialistes" },
        info: {
            en: "A group hands the call from one agent to another by changing prompt and model. In real time the session opens with one model and cannot change it.",
            fr: "Un groupe passe l'appel d'un agent à l'autre en changeant de prompt et de modèle. En temps réel, la session est ouverte avec un seul modèle et ne peut pas en changer.",
        },
    },
];

export type Structure = "groupe" | "un";
export type Depart = "builder" | "recette" | "vide";
export type Cerveau = "chaine" | "temps-reel";

const carte = (actif: boolean, desactive = false) =>
    `rounded-xl border text-left ${desactive ? "cursor-not-allowed opacity-45" : "cursor-pointer"} ${actif ? "border-(--acc) ring-1 ring-(--acc)" : desactive ? "" : "hover:bg-muted/50"}`;

export type AgentCree = { workflowId: number; nom: string };

export function FenetreCreationAgent({
    ouvert,
    fermer,
    dossierId = null,
    organisationId = null,
    surCree,
    departParDefaut = "builder",
}: {
    ouvert: boolean;
    fermer: () => void;
    dossierId?: number | null;
    /** Le client où l'agent naît (installation d'un client) ; absent : l'espace de l'adresse. */
    organisationId?: number | null;
    /** Absent : l'agent créé s'ouvre. Présent : rien ne s'ouvre, l'appelant reçoit l'agent. */
    surCree?: (agent: AgentCree) => void | Promise<void>;
    departParDefaut?: Depart;
}) {
    const { t } = useLangue();
    const router = useRouter();
    const [structure, setStructure] = useState<Structure>("groupe");
    const [depart, setDepart] = useState<Depart>(departParDefaut);
    const [cerveau, setCerveau] = useState<Cerveau>("chaine");
    const [nom, setNom] = useState("");
    const [nomTouche, setNomTouche] = useState(false);
    const [description, setDescription] = useState("");
    const [enCours, setEnCours] = useState(false);
    const tempsReel = cerveau === "temps-reel";
    const structureEffective: Structure = tempsReel ? "un" : structure;
    const entetes = organisationId ? { [ENTETE_ORGANISATION]: String(organisationId) } : undefined;

    useEffect(() => {
        if (ouvert) setDepart(departParDefaut);
    }, [ouvert, departParDefaut]);

    const poserLeTempsReel = async (workflowId: number, configurations: WorkflowConfigurationDefaults | null | undefined) => {
        const actuelles = (configurations ?? {}) as Record<string, unknown>;
        const surcharges = (actuelles.model_overrides as Record<string, unknown> | undefined) ?? {};
        const reponse = await updateWorkflowApiV1WorkflowWorkflowIdPut({
            path: { workflow_id: workflowId },
            headers: entetes,
            body: { workflow_configurations: { ...actuelles, model_overrides: { ...surcharges, is_realtime: true } } as WorkflowConfigurationDefaults },
        });
        if (reponse.error) notifier.avertissement(T.tempsReelNonPose, { erreur: reponse.error });
    };

    const creer = async () => {
        const propre = nom.trim();
        setNomTouche(true);
        if (!propre || enCours) return;
        setEnCours(true);
        const suffixe = depart === "builder" ? "?builder=1" : "";
        try {
            let cree: AgentCree;
            if (structureEffective === "groupe") {
                const reponse = await creerUnGroupeApiV1WorkflowGroupePost({ headers: entetes, body: { name: propre, folder_id: dossierId, recette: null } });
                if (reponse.error || !reponse.data) throw reponse.error ?? new Error("groupe");
                cree = { workflowId: reponse.data.workflow_id, nom: propre };
            } else {
                const reponse = await createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost({
                    headers: entetes,
                    body: { call_type: "inbound", use_case: propre, activity_description: depart === "builder" ? description.trim() : "", recette: null },
                });
                if (reponse.error || !reponse.data?.id) throw reponse.error ?? new Error("agent");
                // Le serveur nomme l'agent d'après le cas d'usage ; le nom donné ici est celui qu'on garde.
                await updateWorkflowApiV1WorkflowWorkflowIdPut({ path: { workflow_id: reponse.data.id }, headers: entetes, body: { name: propre } });
                if (tempsReel) await poserLeTempsReel(reponse.data.id, reponse.data.workflow_configurations);
                cree = { workflowId: reponse.data.id, nom: propre };
            }
            fermer();
            setNom("");
            setNomTouche(false);
            setDescription("");
            if (surCree) await surCree(cree);
            else {
                notifier.succes(T.cree);
                router.push(`${adresseOnglet(cree.workflowId, "parcours")}${suffixe}`);
            }
        } catch (erreur) {
            notifier.echec(T.echec, { erreur });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog centree open={ouvert} onOpenChange={(o) => !o && !enCours && fermer()}>
            <DialogContent className="flex max-h-[90vh] flex-col overflow-hidden sm:max-w-2xl" data-modale="creation-d-agent">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {t(T.titre)}
                        <Info>{t(T.info)}</Info>
                    </DialogTitle>
                    <DialogDescription className="sr-only">{t(T.resume)}</DialogDescription>
                </DialogHeader>
                <div className="-mx-1 min-h-0 flex-1 space-y-5 overflow-auto px-1">
                    <div className="space-y-2">
                        <label htmlFor="nom-du-nouvel-agent" className="text-sm font-medium">
                            {t(T.nom)}
                        </label>
                        <Input
                            id="nom-du-nouvel-agent"
                            value={nom}
                            maxLength={100}
                            onChange={(e) => setNom(e.target.value)}
                            onBlur={() => setNomTouche(true)}
                            aria-invalid={nomTouche && !nom.trim()}
                            aria-describedby={nomTouche && !nom.trim() ? "nom-du-nouvel-agent-erreur" : undefined}
                        />
                        <ErreurChamp id="nom-du-nouvel-agent-erreur">{nomTouche && !nom.trim() ? t(T.nomRequis) : null}</ErreurChamp>
                    </div>
                    <div className="space-y-2">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t(T.structure)}
                            <Info>{t(T.structureInfo)}</Info>
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { id: "groupe" as const, icone: Users2, titre: T.groupe, phrase: T.groupePhrase },
                                { id: "un" as const, icone: Workflow, titre: T.un, phrase: T.unPhrase },
                            ].map((c) => {
                                const bloque = tempsReel && c.id === "groupe";
                                return (
                                    <button
                                        key={c.id}
                                        type="button"
                                        disabled={bloque}
                                        data-structure={c.id}
                                        aria-pressed={structureEffective === c.id}
                                        onClick={() => setStructure(c.id)}
                                        className={`${carte(structureEffective === c.id, bloque)} p-4`}
                                    >
                                        <c.icone className="mb-2 size-5 text-muted-foreground" />
                                        <p className="flex items-center gap-1.5 text-sm font-medium">
                                            {t(c.titre)}
                                            {bloque && <Info>{t(T.groupeBloque)}</Info>}
                                        </p>
                                        <p className="text-xs text-muted-foreground">{t(c.phrase)}</p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    <div className="space-y-2" data-section="cerveau">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t(T.cerveau)}
                            <Info>{t(T.cerveauInfo)}</Info>
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { id: "chaine" as const, titre: T.chaine, phrase: T.chainePhrase },
                                { id: "temps-reel" as const, titre: T.tempsReel, phrase: T.tempsReelPhrase },
                            ].map((c) => (
                                <button
                                    key={c.id}
                                    type="button"
                                    data-cerveau={c.id}
                                    aria-pressed={cerveau === c.id}
                                    onClick={() => setCerveau(c.id)}
                                    className={`${carte(cerveau === c.id)} p-3`}
                                >
                                    <p className="text-sm font-medium">{t(c.titre)}</p>
                                    <p className="text-[11px] leading-snug text-muted-foreground">{t(c.phrase)}</p>
                                </button>
                            ))}
                        </div>
                        {tempsReel && (
                            <div className="pt-1" data-section="chaine-seulement">
                                <p className="flex items-center gap-1.5 pb-1 text-xs font-medium text-muted-foreground">
                                    {t(T.chaineSeulement)}
                                    <Info>{t(T.chaineSeulementInfo)}</Info>
                                </p>
                                <div className="divide-y border-y">
                                    {CHAINE_SEULEMENT.map((c) => (
                                        <div key={c.nom.fr} className="flex cursor-not-allowed items-center gap-1.5 py-1.5 text-sm text-muted-foreground/70">
                                            <span className="flex-1">{t(c.nom)}</span>
                                            <Info>{t(c.info)}</Info>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                    <div className="space-y-2">
                        <p className="text-sm font-medium">{t(T.depart)}</p>
                        <div className="grid grid-cols-3 gap-3">
                            {[
                                { id: "builder" as const, icone: Sparkles, titre: T.builder, phrase: T.builderPhrase },
                                { id: "recette" as const, icone: FileText, titre: T.recette, phrase: T.recettePhrase },
                                { id: "vide" as const, icone: Plus, titre: T.vide, phrase: T.videPhrase },
                            ].map((c) => (
                                <button
                                    key={c.id}
                                    type="button"
                                    data-depart={c.id}
                                    aria-pressed={depart === c.id}
                                    onClick={() => setDepart(c.id)}
                                    className={`${carte(depart === c.id)} p-3`}
                                >
                                    <c.icone className="mb-2 size-4 text-muted-foreground" />
                                    <p className="text-sm font-medium">{t(c.titre)}</p>
                                    <p className="text-[11px] leading-snug text-muted-foreground">{t(c.phrase)}</p>
                                </button>
                            ))}
                        </div>
                    </div>
                    {depart === "builder" && structureEffective === "un" && (
                        <Textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            aria-label={t(T.description)}
                            placeholder={t(T.description)}
                            className="min-h-20"
                        />
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" className="cursor-pointer" onClick={fermer} disabled={enCours}>
                        {t(T.annuler)}
                    </Button>
                    <Button className="cursor-pointer" onClick={() => void creer()} disabled={enCours}>
                        {enCours ? t(T.enCours) : depart === "builder" ? t(T.lancer) : t(T.creer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
