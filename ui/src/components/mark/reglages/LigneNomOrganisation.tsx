"use client";

/**
 * [.mark] Correctifs d'écran, point 14 : la ligne « Nom » de Réglages › Général d'un client. Le nom d'affichage de l'espace se
 * renomme ici ; le serveur sait déjà (`PUT /espaces/{organization_id}`, `nom_affichage`, journalisé), et `reglerEspace`
 * signale le changement : le sélecteur d'espace, les miettes et le menu lisent le nom à nouveau sans recharger la page.
 *
 * La fenêtre s'ouvre dans le panneau de droite. Un nom vide est refusé sous le champ (pas de notification : c'est une erreur de
 * saisie) ; le résultat de l'enregistrement se dit par une notification passagère, jamais par le texte du serveur.
 */
import { Pencil } from "lucide-react";
import { useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Button } from "@/components/ui/button";
import { reglerEspace } from "@/lib/espaces";

/** Le serveur borne le nom à 120 caractères (`NOM_MAX`). */
export const NOM_ORGANISATION_MAX = 120;

const T = {
    renommer: { en: "Rename", fr: "Renommer" },
    titre: { en: "Rename the organization", fr: "Renommer l'organisation" },
    champ: { en: "Name", fr: "Nom" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    vide: { en: "Give the organization a name.", fr: "Donnez un nom à l'organisation." },
    trop: { en: `The name holds ${NOM_ORGANISATION_MAX} characters at most.`, fr: `Le nom tient en ${NOM_ORGANISATION_MAX} caractères au plus.` },
    succes: { en: "Organization renamed.", fr: "Organisation renommée." },
    echec: { en: "The name was not changed. Try again.", fr: "Le nom n'a pas été changé. Réessayez." },
} satisfies Record<string, Texte>;

export function LigneNomOrganisation({ id, nom }: { id: number; nom: string | null }) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);

    return (
        <span className="flex flex-wrap items-center gap-x-2" data-nom-organisation>
            <span className="min-w-0 truncate">{nom ?? "…"}</span>
            <Button type="button" variant="ghost" size="sm" className="cursor-pointer" onClick={() => setOuverte(true)} aria-haspopup="dialog">
                <Pencil className="mr-1 size-3.5" aria-hidden /> {t(T.renommer)}
            </Button>
            <FenetreChamps
                ouverte={ouverte}
                fermer={() => setOuverte(false)}
                titre={t(T.titre)}
                valider={t(T.enregistrer)}
                sections={[{ champs: [{ id: "nom", t: "texte", l: t(T.champ), v: nom ?? "" }] }]}
                verifier={(v) => {
                    const saisi = String(v.nom ?? "").trim();
                    if (!saisi) return { nom: t(T.vide) };
                    if (saisi.length > NOM_ORGANISATION_MAX) return { nom: t(T.trop) };
                    return null;
                }}
                onValider={async (v) => {
                    try {
                        await reglerEspace(id, { nom_affichage: String(v.nom).trim() });
                    } catch (e) {
                        notifier.echec(T.echec, { erreur: e });
                        return false;
                    }
                    notifier.succes(T.succes);
                }}
            />
        </span>
    );
}
