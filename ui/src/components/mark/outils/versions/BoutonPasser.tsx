"use client";

/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : « Passer à la v5 », partagé par la fenêtre de l'outil et par l'étape.
 * Le bouton ouvre une petite fenêtre centrée (un geste qui touche un vrai logiciel : on confirme) ; confirmer écrit l'épingle dans le
 * BROUILLON de l'agent et de la branche, jamais dans une version publiée. La règle est dite en bulle, nulle part en dur.
 */
import { useState } from "react";

import { passerAUneVersionApiV1BuilderOutilsAgentWorkflowIdVersionPut } from "@/client/sdk.gen";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { useLangue } from "../../langue/langue";
import { Info } from "../../studio/marques";
import { REGLE_VERSIONS_OUTIL, T } from "./textes";
import { signalerUnChangementDeVersion } from "./useVersionsOutils";

export interface CiblePassage {
    toolUuid: string;
    outil: string;
    workflowId: number;
    agent: string;
    branche: string;
    /** Absent : la branche ouverte par la requête (l'éditeur de l'agent) ; sinon la branche nommée (fenêtre de l'outil). */
    brancheId?: number | null;
    suivreLEnTete?: boolean;
    de: number;
    vers: number;
}

export function BoutonPasser({ cible, variante = "outline" }: { cible: CiblePassage; variante?: "outline" | "ghost" }) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    const [enCours, setEnCours] = useState(false);

    const confirmer = async () => {
        setEnCours(true);
        const r = await passerAUneVersionApiV1BuilderOutilsAgentWorkflowIdVersionPut({
            path: { workflow_id: cible.workflowId },
            body: {
                tool_uuid: cible.toolUuid,
                version: cible.vers,
                suivre_l_en_tete: cible.suivreLEnTete ?? false,
                branche_id: cible.brancheId ?? null,
            },
        });
        setEnCours(false);
        if (r.error) {
            echecAffiche(r.error, T.echec);
            return;
        }
        notifier.succes(T.ecrite(cible.outil, cible.vers, cible.agent, cible.branche));
        setOuvert(false);
        signalerUnChangementDeVersion();
    };

    return (
        <>
            <Button variant={variante} size="sm" className="h-7 shrink-0 cursor-pointer" onClick={() => setOuvert(true)} data-passer-version={cible.toolUuid}>
                {t(T.passerA(cible.vers))}
            </Button>
            <Dialog centree open={ouvert} onOpenChange={(o) => !o && !enCours && setOuvert(false)}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            {t(T.titreConfirmation(cible.vers))}
                            <Info>{t(REGLE_VERSIONS_OUTIL)}</Info>
                        </DialogTitle>
                        <DialogDescription className="sr-only">{t(T.description)}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 text-sm">
                        <p>{t(T.corps(cible.outil, cible.de, cible.vers, cible.agent, cible.branche))}</p>
                        <p className="text-muted-foreground">{t(T.corpsAide(cible.de))}</p>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" className="cursor-pointer" onClick={() => setOuvert(false)} disabled={enCours}>
                            {t(T.annuler)}
                        </Button>
                        <Button className="cursor-pointer" onClick={() => void confirmer()} disabled={enCours} data-confirmer-passage>
                            {t(T.passerA(cible.vers))}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
