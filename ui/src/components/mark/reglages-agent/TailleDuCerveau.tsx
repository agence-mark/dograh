"use client";

/**
 * [.mark] Lot « façon Tala par motif » (T3) : « Taille supportée par le cerveau », dans le thème Briques, sous le cerveau.
 *
 * - `cerveau_plafond_prompt` : le plus long prompt (en caractères) que le cerveau tient bien. Au-delà, la règle `longueur` PRÉVIENT
 *   à la publication, elle ne bloque jamais ;
 * - `cerveau_poids_max` : le poids d'une réplique (prompt général + prompt de l'étape + conditions de ses sorties). Au-delà, la ligne
 *   de « Poids de l'agent » passe en « à relire ».
 *
 * Saisie libre, VIDE = AUCUN seuil (aucun fournisseur n'en publie : il se mesure au banc). Les deux suivent le cerveau : un modèle
 * de réglages les fige avec lui. On montre le nombre de caractères d'aujourd'hui pour s'y repérer.
 */
import { useEffect, useState } from "react";

import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { attributsDeBorne, texteHorsBornes } from "../bornes-reglages";
import { ChampReglage, texteBornes } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";
import type { Enregistrer } from "./enregistrement";

type CleDeSeuil = "cerveau_plafond_prompt" | "cerveau_poids_max";

const textes = {
    cerveau_plafond_prompt: {
        libelle: { en: "Longest prompt (characters)", fr: "Prompt le plus long (caractères)" } as Texte,
        aide: {
            en: "The longest prompt this brain handles well. A longer prompt only warns at publication, it never blocks. Empty: no threshold, the check stays silent. Providers do not publish this figure: it is measured on the bench.",
            fr: "Le prompt le plus long que ce cerveau tient bien. Un prompt plus long prévient seulement à la publication, il ne bloque jamais. Vide : aucun seuil, le contrôle reste muet. Les fournisseurs ne publient pas ce chiffre : il se mesure au banc.",
        } as Texte,
        enregistre: { en: "Longest prompt saved.", fr: "Prompt le plus long enregistré." } as Texte,
        bouton: { en: "Save the longest prompt", fr: "Enregistrer le prompt le plus long" } as Texte,
    },
    cerveau_poids_max: {
        libelle: { en: "Heaviest reply (characters)", fr: "Réplique la plus lourde (caractères)" } as Texte,
        aide: {
            en: "What the brain reads at each reply: general prompt + step prompt + conditions of its exits. Above it, a step shows « to read again » in the Publish window; publishing stays possible. Empty: no threshold, only the numbers are shown.",
            fr: "Ce que le cerveau lit à chaque réplique : prompt général + prompt de l'étape + conditions de ses sorties. Au-delà, une étape passe en « à relire » dans la fenêtre Publier ; la publication reste possible. Vide : aucun seuil, seuls les nombres sont montrés.",
        } as Texte,
        enregistre: { en: "Heaviest reply saved.", fr: "Réplique la plus lourde enregistrée." } as Texte,
        bouton: { en: "Save the heaviest reply", fr: "Enregistrer la réplique la plus lourde" } as Texte,
    },
} satisfies Record<CleDeSeuil, Record<string, Texte>>;

function ChampDeSeuil({
    cle,
    resolue,
    enregistrer,
    desactive,
}: {
    cle: CleDeSeuil;
    resolue: WorkflowConfigurations;
    enregistrer: (patch: Partial<WorkflowConfigurations>, message: Texte) => Promise<void>;
    desactive: boolean;
}) {
    const { t } = useLangue();
    const enregistre = resolue[cle] ?? null;
    const [saisie, setSaisie] = useState(enregistre === null ? "" : String(enregistre));
    useEffect(() => setSaisie(enregistre === null ? "" : String(enregistre)), [enregistre]);
    const nombre = saisie.trim() === "" ? null : Number(saisie.replace(",", "."));
    const entier = nombre === null || Number.isInteger(nombre);
    const erreur = nombre === null ? null : !entier ? { en: "Enter a whole number.", fr: "Saisissez un nombre entier." } : texteHorsBornes(cle, nombre);
    const x = textes[cle];
    return (
        <ChampReglage cle={cle} idControle={cle} libelle={x.libelle} bornes={texteBornes(cle)} erreur={erreur} aides={[x.aide]}>
            <div className="flex items-center gap-2">
                <Input
                    id={cle}
                    type="number"
                    inputMode="numeric"
                    className="max-w-40"
                    placeholder={t({ en: "No threshold", fr: "Aucun seuil" })}
                    {...attributsDeBorne(cle)}
                    value={saisie}
                    onChange={(e) => setSaisie(e.target.value)}
                />
                <Button variant="outline" size="sm" disabled={desactive || erreur !== null || nombre === enregistre} onClick={() => void enregistrer({ [cle]: nombre }, x.enregistre)}>
                    {t(x.bouton)}
                </Button>
            </div>
        </ChampReglage>
    );
}

export const TailleDuCerveau = ({ resolue, workflowName, onSave }: { resolue: WorkflowConfigurations; workflowName: string; onSave: Enregistrer }) => {
    const { t } = useLangue();
    const [enCours, setEnCours] = useState(false);
    const enregistrer = async (patch: Partial<WorkflowConfigurations>, message: Texte) => {
        setEnCours(true);
        try {
            await onSave({ ...resolue, ...patch }, workflowName);
            notifier.succes(message, { publier: true });
        } finally {
            setEnCours(false);
        }
    };
    return (
        <Intertitre
            id="briques-taille"
            titre={{ en: "Size the brain handles", fr: "Taille supportée par le cerveau" }}
            description={{
                en: "Thresholds that follow the brain, free to fill in and empty by default: no threshold. They warn at publication, they never block. A settings template freezes them with the brain.",
                fr: "Des seuils qui suivent le cerveau, à saisir librement et vides par défaut : aucun seuil. Ils préviennent à la publication, ils ne bloquent jamais. Un modèle de réglages les fige avec le cerveau.",
            }}
        >
            <ChampDeSeuil cle="cerveau_plafond_prompt" resolue={resolue} enregistrer={enregistrer} desactive={enCours} />
            <ChampDeSeuil cle="cerveau_poids_max" resolue={resolue} enregistrer={enregistrer} desactive={enCours} />
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "The Publish window shows the weight of each step in numbers, with or without a threshold.",
                    fr: "La fenêtre Publier montre le poids de chaque étape en nombres, avec ou sans seuil.",
                })}
            </p>
        </Intertitre>
    );
};
