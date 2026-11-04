"use client";

/**
 * [.mark] K2 : la fenêtre « Nouvel agent », reprise de la maquette (`liste-agents.tsx`, `ModaleCreation`) : la structure (groupe
 * avec spécialistes, un agent), le point de départ (avec le builder, depuis une recette, vide), et pour le builder la
 * description à lui donner. Centrée, corps blanc. Ce que le serveur exige et que la maquette ne montre pas : un nom.
 * « Depuis une recette » est grisé tant que la bibliothèque de structures n'a pas son entrée de création (raison en info-bulle).
 */
import { FileText, Plus, Sparkles, Users2, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
    createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost,
    creerUnGroupeApiV1WorkflowGroupePost,
    listerLesRecettesApiV1BuilderRecettesGet,
    updateWorkflowApiV1WorkflowWorkflowIdPut,
} from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { adresseOnglet } from "./onglets-agent";

const T = {
    titre: { en: "New agent", fr: "Nouvel agent" },
    info: { en: "Created as a draft.", fr: "Créé en brouillon." },
    nom: { en: "Name", fr: "Nom" },
    structure: { en: "Structure", fr: "Structure" },
    groupe: { en: "Group with specialists", fr: "Groupe avec spécialistes" },
    groupePhrase: { en: "A greeter and one specialist per call reason.", fr: "Un accueil, un spécialiste par motif d'appel." },
    un: { en: "One agent", fr: "Un agent" },
    unPhrase: { en: "One prompt and a few steps. For a simple need or the site.", fr: "Un seul prompt et peu d'étapes. Pour un besoin simple ou le site." },
    depart: { en: "Starting point", fr: "Point de départ" },
    builder: { en: "With the builder", fr: "Avec le builder" },
    builderPhrase: { en: "It reads the files, asks its questions, writes the design.", fr: "Il lit les dossiers, pose ses questions, rédige la conception." },
    recette: { en: "From a recipe", fr: "Depuis une recette" },
    recettePhrase: { en: "A structure from the library, to fill in.", fr: "Une structure de la bibliothèque, à remplir." },
    recetteRaison: { en: "Arrives with the library's creation entry.", fr: "Arrive avec l'entrée de création de la bibliothèque." },
    vide: { en: "Empty", fr: "Vide" },
    videPhrase: { en: "Empty graph, neutral template.", fr: "Graphe vierge, gabarit neutre posé." },
    recetteTitre: { en: "Recipe", fr: "Recette" },
    recetteInfo: {
        en: "How the builder builds this agent: its pieces, its method. Read from the library; it can no longer change once a version is published.",
        fr: "La façon dont le builder construit cet agent : ses pièces, sa méthode. Lue dans la bibliothèque ; elle ne change plus une fois une version publiée.",
    },
    nonProuvee: { en: "not proven", fr: "non prouvée" },
    parDefaut: { en: "default", fr: "par défaut" },
    description: { en: "What the company does and what the agent must do, in a few lines.", fr: "Ce que fait l'entreprise et ce que l'agent doit faire, en quelques lignes." },
    annuler: { en: "Cancel", fr: "Annuler" },
    lancer: { en: "Start the builder", fr: "Lancer le builder" },
    creer: { en: "Create the draft", fr: "Créer le brouillon" },
    enCours: { en: "Creating...", fr: "Création..." },
    echec: { en: "Agent not created. Try again.", fr: "Agent non créé. Réessayez." },
} satisfies Record<string, Texte>;

type RecetteProposee = { slug: string; nom: string; quand: string; quand_en?: string; prouvee: boolean };

const carte = (actif: boolean) => `rounded-xl border text-left ${actif ? "border-(--acc) ring-1 ring-(--acc)" : "hover:bg-muted/50"}`;

export function ModaleNouvelAgent({ ouvert, fermer, dossierId = null }: { ouvert: boolean; fermer: () => void; dossierId?: number | null }) {
    const { t } = useLangue();
    const router = useRouter();
    const [structure, setStructure] = useState<"groupe" | "un">("groupe");
    const [depart, setDepart] = useState<"builder" | "vide">("builder");
    const [nom, setNom] = useState("");
    const [description, setDescription] = useState("");
    const [enCours, setEnCours] = useState(false);
    const [recettes, setRecettes] = useState<RecetteProposee[]>([]);
    const [defautRecette, setDefautRecette] = useState<string | null>(null);
    const [recette, setRecette] = useState("");

    // La liste des recettes vient de la bibliothèque (lot M) : aucune n'est écrite ici. Vide ou illisible : la section n'apparaît pas.
    useEffect(() => {
        if (!ouvert) return;
        void listerLesRecettesApiV1BuilderRecettesGet().then((r) => {
            const vue = r.data as { defaut: string | null; recettes: RecetteProposee[] } | undefined;
            if (!vue) return;
            setRecettes(vue.recettes);
            setDefautRecette(vue.defaut);
            setRecette((actuelle) => actuelle || vue.defaut || "");
        });
    }, [ouvert]);

    const creer = async () => {
        const propre = nom.trim();
        if (!propre || enCours) return;
        setEnCours(true);
        const builder = depart === "builder" ? "?builder=1" : "";
        try {
            if (structure === "groupe") {
                const reponse = await creerUnGroupeApiV1WorkflowGroupePost({ body: { name: propre, folder_id: dossierId, recette: recette || null } });
                if (reponse.error || !reponse.data) throw new Error("groupe");
                router.push(`${adresseOnglet(reponse.data.workflow_id, "parcours")}${builder}`);
            } else {
                const reponse = await createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost({
                    body: { call_type: "inbound", use_case: propre, activity_description: depart === "builder" ? description.trim() : "", recette: recette || null },
                });
                if (reponse.error || !reponse.data?.id) throw new Error("agent");
                // Le serveur nomme l'agent d'après le cas d'usage ; le nom donné ici est celui qu'on garde.
                await updateWorkflowApiV1WorkflowWorkflowIdPut({ path: { workflow_id: reponse.data.id }, body: { name: propre } });
                router.push(`${adresseOnglet(reponse.data.id, "parcours")}${builder}`);
            }
            fermer();
            setNom("");
            setDescription("");
        } catch {
            notifier.echec({ fr: T.echec.fr, en: T.echec.en });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog open={ouvert} onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-2xl" data-modale="creation-d-agent">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {t(T.titre)}
                        <Info>{t(T.info)}</Info>
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-5">
                    <div className="space-y-2">
                        <p className="text-sm font-medium">{t(T.nom)}</p>
                        <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t(T.nom)} />
                    </div>
                    <div className="space-y-2">
                        <p className="text-sm font-medium">{t(T.structure)}</p>
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { id: "groupe" as const, icone: Users2, titre: T.groupe, phrase: T.groupePhrase },
                                { id: "un" as const, icone: Workflow, titre: T.un, phrase: T.unPhrase },
                            ].map((c) => (
                                <button key={c.id} type="button" onClick={() => setStructure(c.id)} className={`${carte(structure === c.id)} cursor-pointer p-4`}>
                                    <c.icone className="mb-2 size-5 text-muted-foreground" />
                                    <p className="text-sm font-medium">{t(c.titre)}</p>
                                    <p className="text-xs text-muted-foreground">{t(c.phrase)}</p>
                                </button>
                            ))}
                        </div>
                    </div>
                    {recettes.length > 0 && (
                        <div className="space-y-2" data-section="recette">
                            <p className="flex items-center gap-2 text-sm font-medium">
                                {t(T.recetteTitre)}
                                <Info>{t(T.recetteInfo)}</Info>
                            </p>
                            <div className="grid grid-cols-2 gap-3">
                                {recettes.map((r) => (
                                    <button
                                        key={r.slug}
                                        type="button"
                                        data-recette={r.slug}
                                        aria-pressed={recette === r.slug}
                                        onClick={() => setRecette(r.slug)}
                                        className={`${carte(recette === r.slug)} cursor-pointer p-3`}
                                    >
                                        <p className="text-sm font-medium">
                                            {r.nom}
                                            {r.slug === defautRecette && <span className="ml-2 text-xs font-normal text-muted-foreground">{t(T.parDefaut)}</span>}
                                            {!r.prouvee && <span className="ml-2 text-xs font-normal text-muted-foreground">{t(T.nonProuvee)}</span>}
                                        </p>
                                        {r.quand && <p className="text-[11px] leading-snug text-muted-foreground">{t({ en: r.quand_en || r.quand, fr: r.quand })}</p>}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                    <div className="space-y-2">
                        <p className="text-sm font-medium">{t(T.depart)}</p>
                        <div className="grid grid-cols-3 gap-3">
                            <button type="button" onClick={() => setDepart("builder")} className={`${carte(depart === "builder")} cursor-pointer p-3`}>
                                <Sparkles className="mb-2 size-4 text-muted-foreground" />
                                <p className="text-sm font-medium">{t(T.builder)}</p>
                                <p className="text-[11px] leading-snug text-muted-foreground">{t(T.builderPhrase)}</p>
                            </button>
                            <button type="button" disabled title={t(T.recetteRaison)} className={`${carte(false)} cursor-not-allowed p-3 opacity-50`}>
                                <FileText className="mb-2 size-4 text-muted-foreground" />
                                <p className="text-sm font-medium">{t(T.recette)}</p>
                                <p className="text-[11px] leading-snug text-muted-foreground">{t(T.recettePhrase)}</p>
                            </button>
                            <button type="button" onClick={() => setDepart("vide")} className={`${carte(depart === "vide")} cursor-pointer p-3`}>
                                <Plus className="mb-2 size-4 text-muted-foreground" />
                                <p className="text-sm font-medium">{t(T.vide)}</p>
                                <p className="text-[11px] leading-snug text-muted-foreground">{t(T.videPhrase)}</p>
                            </button>
                        </div>
                    </div>
                    {depart === "builder" && structure === "un" && (
                        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t(T.description)} className="min-h-20" />
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={fermer}>
                        {t(T.annuler)}
                    </Button>
                    <Button onClick={() => void creer()} disabled={!nom.trim() || enCours}>
                        {enCours ? t(T.enCours) : depart === "builder" ? t(T.lancer) : t(T.creer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
