"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A11) : la modale de création d'un agent, à deux cartes.
 *
 * - « Graphe de nœuds » : les deux chemins d'aujourd'hui, inchangés (le constructeur d'agent, la
 *   toile vierge) ;
 * - « Graphe avec agents spécialisés » : crée l'agent principal et son sous-dossier, puis ouvre le
 *   groupe dans la liste. Le nom du groupe est demandé ici.
 *
 * La carte « Monoprompt » viendra avec son chantier. Modale CENTRÉE, jamais un panneau latéral.
 *
 * Chantier builder-agent-vocal, lot 4 (B3) : une case « Démarrer avec le Builder IA » (cochée par défaut) ouvre
 * l'éditeur de l'agent avec le panneau du builder déjà ouvert (`?builder=1`). L'ancien « assistant de création »
 * (générateur de modèle du service hébergé) n'est plus proposé : le builder le remplace ; la carte ne le montre
 * que si l'appelant fournit encore `onConstructeur`.
 */
import { Bot, LayoutTemplate, Network } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { creerUnGroupeApiV1WorkflowGroupePost } from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

const TEXTES = {
    titre: { en: "Create an agent", fr: "Créer un agent" },
    description: { en: "Choose the kind of agent to build.", fr: "Choisissez le type d'agent à construire." },
    noeuds: { en: "Node graph", fr: "Graphe de nœuds" },
    noeudsAide: {
        en: "One agent whose conversation is a graph of steps.",
        fr: "Un seul agent dont la conversation est un graphe d'étapes.",
    },
    constructeur: { en: "Use the agent builder", fr: "Utiliser l'assistant de création" },
    constructeurAide: { en: "AI generates a workflow from your description", fr: "L'IA génère un workflow à partir de votre description" },
    vierge: { en: "Blank canvas", fr: "Page blanche" },
    demarrerAvecLeBuilder: { en: "Start with the Builder AI", fr: "Démarrer avec le Builder IA" },
    demarrerAvecLeBuilderAide: {
        en: "Opens the editor with the Builder AI panel: it reads your documents and builds the draft with you.",
        fr: "Ouvre l'éditeur avec le panneau Builder IA : il lit vos documents et construit le brouillon avec vous.",
    },
    viergeAide: { en: "Start from scratch with an empty workflow", fr: "Partir d'un workflow vide" },
    groupe: { en: "Graph with specialised agents", fr: "Graphe avec agents spécialisés" },
    groupeAide: {
        en: "A main agent that picks up, qualifies and hands the call to the right specialised agent. Creates the main agent and its sub-folder, then opens the group.",
        fr: "Un agent principal qui décroche, qualifie et passe la main au bon agent spécialisé. Crée le principal et son sous-dossier, puis ouvre le groupe.",
    },
    nomDuGroupe: { en: "Group name", fr: "Nom du groupe" },
    creerGroupe: { en: "Create the group", fr: "Créer le groupe" },
    enCours: { en: "Creating...", fr: "Création..." },
    echec: { en: "The group could not be created.", fr: "Le groupe n'a pas pu être créé." },
} satisfies Record<string, Texte>;

export const ModaleCreationAgent = ({
    ouvert,
    onOuvertChange,
    onConstructeur,
    onToileVierge,
    creationEnCours = false,
    dossierParentId = null,
}: {
    ouvert: boolean;
    onOuvertChange: (ouvert: boolean) => void;
    /** Absent: the card does not offer the former template generator (replaced by the Builder AI). */
    onConstructeur?: () => void;
    /** `avecLeBuilder`: the box « Start with the Builder AI » is ticked. */
    onToileVierge: (options: { avecLeBuilder: boolean }) => void;
    creationEnCours?: boolean;
    /** Le dossier dans lequel le groupe prend son sous-dossier (absent : premier niveau). */
    dossierParentId?: number | null;
}) => {
    const { t } = useLangue();
    const router = useRouter();
    const [nom, setNom] = useState("");
    const [enCours, setEnCours] = useState(false);
    const [avecLeBuilder, setAvecLeBuilder] = useState(true);

    const creerLeGroupe = async () => {
        const propre = nom.trim();
        if (!propre || enCours) return;
        setEnCours(true);
        try {
            const reponse = await creerUnGroupeApiV1WorkflowGroupePost({
                body: { name: propre, folder_id: dossierParentId },
            });
            if (reponse.error || !reponse.data) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echec)));
                return;
            }
            onOuvertChange(false);
            setNom("");
            // Ouvre le groupe : la liste, avec le sous-dossier du groupe déplié.
            // Avec le Builder IA : on ouvre l'agent principal, panneau ouvert.
            router.push(avecLeBuilder ? `/workflow/${reponse.data.workflow_id}?builder=1` : `/workflow?dossier=${reponse.data.folder_id}`);
            router.refresh();
        } catch {
            toast.error(t(TEXTES.echec));
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog open={ouvert} onOpenChange={onOuvertChange}>
            <DialogContent className="sm:max-w-2xl" data-modale="creation-d-agent">
                <DialogHeader>
                    <DialogTitle>{t(TEXTES.titre)}</DialogTitle>
                    <DialogDescription>{t(TEXTES.description)}</DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 sm:grid-cols-2">
                    <section className="space-y-3 rounded-lg border p-4" data-carte="graphe-de-noeuds">
                        <h3 className="flex items-center gap-2 text-sm font-semibold">
                            <LayoutTemplate className="h-4 w-4" aria-hidden />
                            {t(TEXTES.noeuds)}
                        </h3>
                        <p className="text-xs text-muted-foreground">{t(TEXTES.noeudsAide)}</p>
                        <div className="space-y-2">
                            {onConstructeur && (
                                <Button type="button" variant="outline" className="h-auto w-full justify-start py-2 text-left" onClick={onConstructeur}>
                                    <Bot className="mr-2 h-4 w-4 shrink-0" aria-hidden />
                                    <span>
                                        <span className="block text-sm font-medium">{t(TEXTES.constructeur)}</span>
                                        <span className="block whitespace-normal text-xs font-normal text-muted-foreground">
                                            {t(TEXTES.constructeurAide)}
                                        </span>
                                    </span>
                                </Button>
                            )}
                            <Button
                                type="button"
                                variant="outline"
                                className="h-auto w-full justify-start py-2 text-left"
                                disabled={creationEnCours}
                                onClick={() => onToileVierge({ avecLeBuilder })}
                            >
                                <LayoutTemplate className="mr-2 h-4 w-4 shrink-0" aria-hidden />
                                <span>
                                    <span className="block text-sm font-medium">{t(TEXTES.vierge)}</span>
                                    <span className="block whitespace-normal text-xs font-normal text-muted-foreground">
                                        {t(TEXTES.viergeAide)}
                                    </span>
                                </span>
                            </Button>
                        </div>
                    </section>
                    <section className="space-y-3 rounded-lg border p-4" data-carte="graphe-avec-agents-specialises">
                        <h3 className="flex items-center gap-2 text-sm font-semibold">
                            <Network className="h-4 w-4" aria-hidden />
                            {t(TEXTES.groupe)}
                        </h3>
                        <p className="text-xs text-muted-foreground">{t(TEXTES.groupeAide)}</p>
                        <div className="space-y-2">
                            <Label htmlFor="nom-du-groupe" className="text-xs">
                                {t(TEXTES.nomDuGroupe)}
                            </Label>
                            <Input
                                id="nom-du-groupe"
                                value={nom}
                                maxLength={100}
                                onChange={(e) => setNom(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                        e.preventDefault();
                                        void creerLeGroupe();
                                    }
                                }}
                            />
                            <Button type="button" className="w-full" disabled={!nom.trim() || enCours} onClick={() => void creerLeGroupe()}>
                                {enCours ? t(TEXTES.enCours) : t(TEXTES.creerGroupe)}
                            </Button>
                        </div>
                    </section>
                </div>
                <label className="flex items-start gap-2 rounded-lg border p-3 text-sm" htmlFor="demarrer-avec-le-builder">
                    <input
                        id="demarrer-avec-le-builder"
                        type="checkbox"
                        className="mt-0.5 h-4 w-4"
                        checked={avecLeBuilder}
                        onChange={(e) => setAvecLeBuilder(e.target.checked)}
                    />
                    <span>
                        <span className="block font-medium">{t(TEXTES.demarrerAvecLeBuilder)}</span>
                        <span className="block text-xs text-muted-foreground">{t(TEXTES.demarrerAvecLeBuilderAide)}</span>
                    </span>
                </label>
            </DialogContent>
        </Dialog>
    );
};
