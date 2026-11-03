"use client";

/**
 * [.mark] Lot M : les deux options de la construction, dans les réglages du builder. Elles s'enregistrent tout de suite (une ligne à
 * part du cerveau : « Enregistrer » du cerveau ne les touche pas).
 *  - Sauvegarde avant modification (éteinte par défaut) : le builder ne modifie pas un agent existant avant une sauvegarde ou un refus ;
 *  - Recette par défaut : celle que la fenêtre « Nouvel agent » propose, lue dans la bibliothèque.
 * Réservé à l'équipe .mark (le serveur décide) : sans réponse du serveur, rien ne s'affiche. Conçu sans maquette.
 */
import { useEffect, useState } from "react";

import { lireLesOptionsApiV1BuilderOptionsGet, listerLesRecettesApiV1BuilderRecettesGet, reglerLesOptionsApiV1BuilderOptionsPut } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { optionsPartagees } from "@/components/mark/reglages/lectures-partagees";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Info } from "@/components/mark/studio/marques";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

const T = {
    sauvegarde: { en: "Backup before the first change", fr: "Sauvegarde avant la première modification" },
    sauvegardeInfo: {
        en: "Off by default. On, the builder does not change an existing agent until a backup of its graph is taken or you decline it. Settings (phrases, lexicon) are not part of the backup.",
        fr: "Éteinte par défaut. Allumée, le builder ne modifie pas un agent existant avant qu'une sauvegarde de son graphe soit prise ou que vous la refusiez. Les réglages (phrases, lexique) ne sont pas dans la sauvegarde.",
    },
    recette: { en: "Default recipe", fr: "Recette par défaut" },
    recetteInfo: {
        en: "The recipe offered first when an agent is created. Empty: the one the library marks as the starting default.",
        fr: "La recette proposée d'abord à la création d'un agent. Vide : celle que la bibliothèque marque comme défaut de départ.",
    },
    aucune: { en: "Starting default", fr: "Défaut de départ" },
    echec: { en: "The option could not be saved.", fr: "L'option n'a pas pu être enregistrée." },
    ok: { en: "Option saved.", fr: "Option enregistrée." },
} satisfies Record<string, Texte>;

type Options = { sauvegarde_avant_modification: boolean; recette_par_defaut: string };

export function OptionsDeConstruction() {
    const { t } = useLangue();
    // [.mark] C4 : les options sont lues une fois pour toute la page des Réglages (avec l'onglet Builder IA).
    const { valeur: lues, poser: poserOptions } = optionsPartagees.useLecture();
    const options = lues as Options | null;
    const [recettes, setRecettes] = useState<{ slug: string; nom: string }[]>([]);

    useEffect(() => {
        void listerLesRecettesApiV1BuilderRecettesGet().then((r) => {
            const liste = (r?.data as { recettes: { slug: string; nom: string }[] } | undefined)?.recettes;
            if (liste) setRecettes(liste);
        });
    }, []);

    if (!options) return null;

    // On relit l'état du serveur et on ne change QUE le champ voulu : les interrupteurs du builder (Portes) vivent dans la même ligne
    // et ne doivent jamais être écrasés par une copie périmée.
    const enregistrer = async (morceau: Partial<Options>) => {
        const frais = await lireLesOptionsApiV1BuilderOptionsGet();
        const base = (frais?.data as Options | undefined) ?? options;
        const r = await reglerLesOptionsApiV1BuilderOptionsPut({ body: { ...base, ...morceau } });
        if (r.error || !r.data) return notifier.echec(T.echec);
        poserOptions(r.data);
        notifier.succes(T.ok);
    };

    return (
        <div className="space-y-3" data-section="options-de-construction">
            <div className="flex items-center justify-between gap-3">
                <Label htmlFor="option-sauvegarde" className="flex items-center gap-1.5">
                    {t(T.sauvegarde)}
                    <Info>{t(T.sauvegardeInfo)}</Info>
                </Label>
                <Switch
                    id="option-sauvegarde"
                    aria-label={t(T.sauvegarde)}
                    checked={options.sauvegarde_avant_modification}
                    onCheckedChange={(valeur) => void enregistrer({ sauvegarde_avant_modification: valeur })}
                />
            </div>
            {recettes.length > 0 && (
                <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="option-recette" className="flex items-center gap-1.5">
                        {t(T.recette)}
                        <Info>{t(T.recetteInfo)}</Info>
                    </Label>
                    <ListeDeroulante
                        id="option-recette"
                        className="h-9 cursor-pointer rounded-md border bg-background px-2 text-sm"
                        value={options.recette_par_defaut}
                        onChange={(e) => void enregistrer({ recette_par_defaut: e.target.value })}
                    >
                        <option value="">{t(T.aucune)}</option>
                        {recettes.map((r) => (
                            <option key={r.slug} value={r.slug}>
                                {r.nom}
                            </option>
                        ))}
                    </ListeDeroulante>
                </div>
            )}
        </div>
    );
}
