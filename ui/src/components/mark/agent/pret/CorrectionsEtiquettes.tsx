"use client";

/**
 * [.mark] Builder partie 3, lots 8 et 22 : sous la ligne « Étiquettes des prompts » (ou « Blocs à jour ») de « Prêt à publier »,
 * chaque étiquette en erreur, le prompt qui la porte et sa correction en un clic (« Rattacher l'outil à l'étape », « Passer à la
 * version N », « Suivre la dernière version », « Retirer l'étiquette »), écrite dans le BROUILLON (rien n'est publié).
 */
import { useParams } from "next/navigation";
import { useState } from "react";

import { corrigerUneEtiquetteApiV1MarkEtiquettesPromptWorkflowIdCorrigerPost } from "@/client/sdk.gen";
import type { CorrectionVue } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";

import { useLangue } from "../../langue/langue";
import { relireLesEtiquettes, useCatalogueEtiquettes } from "../../variables/useCatalogueEtiquettes";
import { useRecalculDuPret } from "./recalcul";

const LIBELLES: Record<string, (c: CorrectionVue) => { en: string; fr: string }> = {
    rattacher: () => ({ en: "Attach the tool to the step", fr: "Rattacher l'outil à l'étape" }),
    retirer: () => ({ en: "Remove the label", fr: "Retirer l'étiquette" }),
    suivre: () => ({ en: "Follow the latest version", fr: "Suivre la dernière version" }),
    passer_version: (c) => ({ en: `Stay on version ${c.version ?? ""}`, fr: `Passer à la version ${c.version ?? ""}` }),
};

export function CorrectionsEtiquettes({ bloquants }: { bloquants: boolean }) {
    const { t } = useLangue();
    const params = useParams<{ workflowId?: string; id?: string }>();
    const agent = Number(params?.workflowId ?? params?.id);
    const { problemes, lu } = useCatalogueEtiquettes();
    const recalculer = useRecalculDuPret((s) => s.demander);
    const [enCours, setEnCours] = useState(false);
    const lignes = problemes.filter((p) => (p.bloquant ?? true) === bloquants);
    if (!lu || lignes.length === 0 || !Number.isFinite(agent)) return null;

    const corriger = async (c: CorrectionVue) => {
        if (enCours) return;
        setEnCours(true);
        try {
            const r = await corrigerUneEtiquetteApiV1MarkEtiquettesPromptWorkflowIdCorrigerPost({
                path: { workflow_id: agent },
                body: { type: c.type as "retirer", cle: c.cle, champ: c.champ ?? null, noeud_id: c.noeud_id ?? null, version: c.version ?? null },
            });
            if (r.error) {
                notifier.echec(
                    { fr: "Correction impossible : le brouillon a changé. La liste est relue.", en: "Could not fix: the draft changed. The list is read again." },
                    { erreur: r.error },
                );
            } else {
                notifier.succes({ fr: "Étiquette corrigée dans le brouillon. Rien n'est publié.", en: "Label fixed in the draft. Nothing is published." });
            }
            relireLesEtiquettes();
            recalculer();
        } finally {
            setEnCours(false);
        }
    };

    return (
        <ul className="mt-1.5 space-y-2" data-testid="etiquettes-en-erreur">
            {lignes.map((p) => (
                <li key={`${p.cle}-${p.champ}`} className="rounded-md bg-muted/50 px-2 py-1.5 text-xs" data-etiquette={p.cle}>
                    <p>
                        <span className="font-medium">{p.etape ?? t({ en: "Settings", fr: "Réglages" })}</span> · {p.message}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                        {(p.corrections ?? []).map((c, i) => (
                            <Button
                                key={`${c.type}-${i}`}
                                size="sm"
                                variant={i === 0 && c.type !== "retirer" ? "default" : "outline"}
                                className="h-6 text-xs"
                                disabled={enCours}
                                data-correction-etiquette={c.type}
                                onClick={() => void corriger(c)}
                            >
                                {t(LIBELLES[c.type]?.(c) ?? { en: c.libelle, fr: c.libelle })}
                            </Button>
                        ))}
                    </div>
                </li>
            ))}
        </ul>
    );
}
