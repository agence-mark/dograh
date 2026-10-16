"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A11) : la vue d'un groupe dans un dossier de la liste
 * d'agents. La carte du principal (son nom, ses numéros, sa fiche) avec « + Agent spécialisé » et
 * « Publier le groupe », puis ses spécialisés dessous, chacun avec son badge « Spécialisé de … ».
 * Un agent seul garde sa ligne d'avant, sans carte.
 *
 * Les lignes sont celles de la liste d'origine (modifier, dupliquer, déplacer, archiver) : la vue ne
 * les refait pas, elle les range sous la carte.
 */
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { creerUnSpecialiseApiV1WorkflowWorkflowIdGroupeSpecialisePost } from "@/client/sdk.gen";
import type { FolderResponse, WorkflowListResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { detailFromError } from "@/lib/apiError";

import { WorkflowTable } from "../../workflow/WorkflowTable";
import { type Texte, useLangue } from "../langue/langue";
import type { RoleAffiche } from "./BadgeGroupe";
import { DialogueNom } from "./DialogueNom";
import { BoutonPublierLeGroupe } from "./PublierLeGroupe";

const TEXTES = {
    groupe: { en: "Group", fr: "Groupe" },
    numeros: { en: "Numbers", fr: "Numéros" },
    aucunNumero: { en: "no number", fr: "aucun numéro" },
    fiche: { en: "Record", fr: "Fiche" },
    aucuneFiche: { en: "no record", fr: "aucune fiche" },
    ajouter: { en: "Agent", fr: "Agent spécialisé" },
    titreCreation: { en: "New specialised agent", fr: "Nouvel agent spécialisé" },
    descriptionCreation: {
        en: "It starts with three steps (qualification, contact details, return to the main agent), the common settings of the main agent, and a hand-over tool on the main agent's qualification step.",
        fr: "Il démarre avec trois étapes (qualification, coordonnées, retour au principal), les réglages communs du principal, et un outil de passation sur l'étape de qualification du principal.",
    },
    nomDuSpecialise: { en: "Agent name", fr: "Nom de l'agent" },
    creer: { en: "Create the agent", fr: "Créer l'agent" },
    cree: { en: "Specialised agent created.", fr: "Agent spécialisé créé." },
    echec: { en: "The specialised agent could not be created.", fr: "L'agent spécialisé n'a pas pu être créé." },
    aucunSpecialise: { en: "No specialised agent yet.", fr: "Aucun agent spécialisé pour l'instant." },
} satisfies Record<string, Texte>;

export interface InfoServie {
    numeros: string[];
    etablissementId: string | null;
}

export const VueGroupe = ({
    principal,
    specialises,
    roles,
    servis,
    dossiers,
    dossierId,
}: {
    principal: WorkflowListResponse;
    specialises: WorkflowListResponse[];
    roles: Map<number, RoleAffiche>;
    servis: Map<number, InfoServie>;
    dossiers: FolderResponse[];
    dossierId: number | null;
}) => {
    const { t } = useLangue();
    const router = useRouter();
    const [creation, setCreation] = useState(false);
    const info = servis.get(principal.id);

    const creer = async (nom: string) => {
        try {
            const reponse = await creerUnSpecialiseApiV1WorkflowWorkflowIdGroupeSpecialisePost({
                path: { workflow_id: principal.id },
                body: { name: nom },
            });
            if (reponse.error) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echec)));
                throw new Error("creation");
            }
            toast.success(t(TEXTES.cree));
            router.refresh();
        } catch (erreur) {
            if (!(erreur instanceof Error && erreur.message === "creation")) toast.error(t(TEXTES.echec));
            throw erreur;
        }
    };

    return (
        <div className="space-y-2" data-vue-groupe={principal.id}>
            <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div className="min-w-0 space-y-1">
                        <p className="flex items-center gap-2 text-sm font-semibold">
                            <span className="text-xs font-normal text-muted-foreground">{t(TEXTES.groupe)}</span>
                            <Link href={`/workflow/${principal.id}`} className="truncate underline">
                                {principal.name}
                            </Link>
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {t(TEXTES.numeros)} :{" "}
                            {info && info.numeros.length > 0 ? info.numeros.join(", ") : t(TEXTES.aucunNumero)}
                            {" · "}
                            {t(TEXTES.fiche)} : {info?.etablissementId ?? t(TEXTES.aucuneFiche)}
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <Button type="button" variant="outline" size="sm" onClick={() => setCreation(true)}>
                            <Plus className="mr-2 h-3.5 w-3.5" />
                            {t(TEXTES.ajouter)}
                        </Button>
                        <BoutonPublierLeGroupe principalId={principal.id} onFait={() => router.refresh()} />
                    </div>
                </CardContent>
            </Card>
            <WorkflowTable
                workflows={[principal, ...specialises]}
                showArchived={false}
                folders={dossiers}
                currentFolderId={dossierId}
                roles={roles}
            />
            {specialises.length === 0 && (
                <p className="px-1 text-xs text-muted-foreground">{t(TEXTES.aucunSpecialise)}</p>
            )}
            <DialogueNom
                ouvert={creation}
                onOuvertChange={setCreation}
                titre={TEXTES.titreCreation}
                description={TEXTES.descriptionCreation}
                libelle={TEXTES.nomDuSpecialise}
                valider={TEXTES.creer}
                onValider={creer}
            />
        </div>
    );
};
