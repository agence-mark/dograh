"use client";

/**
 * [.mark] Partie 3, sous-lot 11 (SE-17, E-7) : sous une réponse en texte du builder, un bouton « Copier » (la maquette, `ActionsReponse`).
 * Le texte copié est celui de la réponse, tel quel. Hors presse-papiers disponible, le bouton le dit par une notification.
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";

const T = {
    copier: { en: "Copy", fr: "Copier" },
    copie: { en: "Copied", fr: "Copié" },
    echec: { en: "Could not copy. Select the text and copy it.", fr: "La copie a échoué. Sélectionnez le texte et copiez-le." },
} satisfies Record<string, Texte>;

export function CopierLaReponse({ texte }: { texte: string }) {
    const { t } = useLangue();
    const [copie, setCopie] = useState(false);
    const copier = async () => {
        try {
            await navigator.clipboard.writeText(texte);
        } catch {
            notifier.echec(T.echec);
            return;
        }
        setCopie(true);
        setTimeout(() => setCopie(false), 1500);
    };
    const libelle = copie ? t(T.copie) : t(T.copier);
    return (
        <button
            type="button"
            onClick={() => void copier()}
            aria-label={libelle}
            title={libelle}
            data-copier-la-reponse
            className="-ml-1.5 inline-flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        >
            {copie ? <Check className="size-3.5 text-(--etat-fait)" /> : <Copy className="size-3.5" />}
        </button>
    );
}
