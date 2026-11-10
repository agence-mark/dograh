"use client";

/**
 * [.mark] Correctifs d'écran, point 15 : la ligne « Logo » de Réglages › Général d'un client. Aperçu (le logo, ou l'initiale
 * quand il n'y en a pas), « Remplacer » (« Ajouter un logo » sans logo) et « Retirer » (avec confirmation sur place).
 *
 * Le fichier se choisit par un `<input type="file">` caché et un bouton (convention de `ui/AGENTS.md`). Il est contrôlé ICI avant
 * l'envoi (format lu dans les octets, 1 Mo, côté de 128 à 1024 px, presque carré) et ENCORE par le serveur, qui reste le juge.
 * Une erreur de saisie s'affiche sous le champ ; le résultat de l'envoi se dit par une notification passagère, jamais par le
 * texte du serveur. Les pastilles (sélecteur, liste des clients, en-tête) se relisent seules (`signalerChangementDEspaces`).
 */
import { ImagePlus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { AvatarClient } from "@/components/mark/relation/commun";
import { Button } from "@/components/ui/button";
import { ErreurLogoServeur, poserLogo, retirerLogo } from "@/lib/espaces";
import { type CodeLogo, controlerFichierLogo, LOGO_COTE_CONSEILLE, LOGO_COTE_MAX, LOGO_COTE_MIN } from "@/lib/logo-controle";
import { useAUnLogo } from "@/lib/logos-espaces";

const T = {
    ajouter: { en: "Add a logo", fr: "Ajouter un logo" },
    remplacer: { en: "Replace", fr: "Remplacer" },
    retirer: { en: "Remove", fr: "Retirer" },
    garder: { en: "Keep", fr: "Garder" },
    confirmer: { en: "Remove the logo?", fr: "Retirer le logo ?" },
    aide: {
        en: `PNG, JPEG or WebP, 1 MB at most, almost square, from ${LOGO_COTE_MIN} to ${LOGO_COTE_MAX} px (${LOGO_COTE_CONSEILLE} px recommended). SVG is not accepted.`,
        fr: `PNG, JPEG ou WebP, 1 Mo au plus, presque carré, de ${LOGO_COTE_MIN} à ${LOGO_COTE_MAX} px (${LOGO_COTE_CONSEILLE} px conseillé). Le SVG n'est pas accepté.`,
    },
    aucun: { en: "No logo: the initial is shown.", fr: "Pas de logo : l'initiale s'affiche." },
    posé: { en: "Logo updated.", fr: "Logo mis à jour." },
    retiré: { en: "Logo removed.", fr: "Logo retiré." },
    echecPose: { en: "The logo was not saved. Try again.", fr: "Le logo n'a pas été enregistré. Réessayez." },
    echecRetrait: { en: "The logo was not removed. Try again.", fr: "Le logo n'a pas été retiré. Réessayez." },
} satisfies Record<string, Texte>;

/** Les refus, sous le champ : ce qui ne va pas ET quoi faire. Les mêmes codes viennent de l'écran et du serveur. */
const ERREURS: Record<CodeLogo, Texte> = {
    logo_vide: { en: "This file is empty. Choose another image.", fr: "Ce fichier est vide. Choisissez une autre image." },
    logo_trop_lourd: { en: "This image is larger than 1 MB. Choose a lighter one.", fr: "Cette image dépasse 1 Mo. Choisissez-en une plus légère." },
    logo_format: {
        en: "Format not accepted. Use a PNG, JPEG or WebP image (not SVG).",
        fr: "Format non accepté. Utilisez une image PNG, JPEG ou WebP (pas de SVG).",
    },
    logo_illisible: { en: "This image cannot be read. Choose another one.", fr: "Cette image est illisible. Choisissez-en une autre." },
    logo_dimensions: {
        en: `Each side must be between ${LOGO_COTE_MIN} and ${LOGO_COTE_MAX} px (${LOGO_COTE_CONSEILLE} px recommended).`,
        fr: `Chaque côté doit faire de ${LOGO_COTE_MIN} à ${LOGO_COTE_MAX} px (${LOGO_COTE_CONSEILLE} px conseillé).`,
    },
    logo_ratio: { en: "The image must be almost square.", fr: "L'image doit être presque carrée." },
};

export function LigneLogoOrganisation({ id, nom }: { id: number; nom: string | null }) {
    const { t } = useLangue();
    const entree = useRef<HTMLInputElement>(null);
    const aUnLogo = useAUnLogo(id);
    const [erreur, setErreur] = useState<Texte | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [confirme, setConfirme] = useState(false);

    const choisi = async (fichier: File | undefined) => {
        if (entree.current) entree.current.value = ""; // le même fichier peut être rechoisi
        if (!fichier) return;
        setErreur(null);
        const controle = await controlerFichierLogo(fichier);
        if (!controle.ok) {
            setErreur(ERREURS[controle.code]);
            return;
        }
        setEnCours(true);
        try {
            await poserLogo(id, fichier);
            notifier.succes(T.posé);
        } catch (e) {
            // Un refus du serveur (type, taille, dimensions) se dit sous le champ ; une panne, par une notification.
            const code = e instanceof ErreurLogoServeur ? (e.code as CodeLogo) : null;
            if (code && code in ERREURS && e instanceof ErreurLogoServeur && e.statut >= 400 && e.statut < 500) setErreur(ERREURS[code]);
            else notifier.echec(T.echecPose, { erreur: e });
        } finally {
            setEnCours(false);
        }
    };

    const retire = async () => {
        setEnCours(true);
        try {
            await retirerLogo(id);
            setConfirme(false);
            setErreur(null);
            notifier.succes(T.retiré);
        } catch (e) {
            notifier.echec(T.echecRetrait, { erreur: e });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <span className="flex flex-col gap-1.5" data-logo-organisation>
            <span className="flex flex-wrap items-center gap-3">
                <AvatarClient id={id} nom={nom ?? ""} taille={48} logo />
                <input
                    ref={entree}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    data-testid="logo-fichier"
                    aria-label={t(aUnLogo ? T.remplacer : T.ajouter)}
                    onChange={(e) => void choisi(e.target.files?.[0])}
                />
                <Button type="button" variant="ghost" size="sm" className="cursor-pointer" disabled={enCours} onClick={() => entree.current?.click()}>
                    <ImagePlus className="mr-1 size-3.5" aria-hidden /> {t(aUnLogo ? T.remplacer : T.ajouter)}
                </Button>
                {aUnLogo &&
                    (confirme ? (
                        <span className="flex items-center gap-2 text-sm">
                            <span>{t(T.confirmer)}</span>
                            <Button type="button" size="sm" variant="outline" className="cursor-pointer" onClick={() => setConfirme(false)}>
                                {t(T.garder)}
                            </Button>
                            <Button type="button" size="sm" variant="destructive" className="cursor-pointer" disabled={enCours} onClick={() => void retire()}>
                                {t(T.retirer)}
                            </Button>
                        </span>
                    ) : (
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="cursor-pointer text-(--marque-danger-texte)"
                            disabled={enCours}
                            onClick={() => setConfirme(true)}
                        >
                            <Trash2 className="mr-1 size-3.5" aria-hidden /> {t(T.retirer)}
                        </Button>
                    ))}
            </span>
            {erreur && (
                <span role="alert" data-erreur-logo className="text-sm text-(--marque-danger-texte)">
                    {t(erreur)}
                </span>
            )}
            <span className="text-xs text-muted-foreground">{t(aUnLogo ? T.aide : { en: `${T.aucun.en} ${T.aide.en}`, fr: `${T.aucun.fr} ${T.aide.fr}` })}</span>
        </span>
    );
}
