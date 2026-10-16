"use client";

/**
 * [.mark] Chantier agents-specialises, lots 10 et 12 : une modale CENTRÉE qui demande un nom
 * (un sous-dossier, un groupe, un agent spécialisé). Une seule zone, le nom ; « Entrée » valide.
 * Même gabarit que la modale de dossier d'origine, avec nos textes dans les deux langues.
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { type Texte, useLangue } from "../langue/langue";

const TEXTES = {
    annuler: { en: "Cancel", fr: "Annuler" },
    enCours: { en: "Saving...", fr: "Enregistrement..." },
} satisfies Record<string, Texte>;

export const DialogueNom = ({
    ouvert,
    onOuvertChange,
    titre,
    description,
    libelle,
    valider,
    onValider,
}: {
    ouvert: boolean;
    onOuvertChange: (ouvert: boolean) => void;
    titre: Texte;
    description?: Texte;
    libelle: Texte;
    valider: Texte;
    /** Résout pour fermer ; lève pour garder la modale ouverte (l'appelant montre son erreur). */
    onValider: (nom: string) => Promise<void>;
}) => {
    const { t } = useLangue();
    const [nom, setNom] = useState("");
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (ouvert) setNom("");
    }, [ouvert]);

    const propre = nom.trim();
    const envoyer = async () => {
        if (!propre || enCours) return;
        setEnCours(true);
        try {
            await onValider(propre);
            onOuvertChange(false);
        } catch {
            // L'appelant a déjà montré l'erreur : la modale reste ouverte.
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog open={ouvert} onOpenChange={onOuvertChange}>
            <DialogContent className="sm:max-w-md" data-modale="nom">
                <DialogHeader>
                    <DialogTitle>{t(titre)}</DialogTitle>
                    {description && <DialogDescription>{t(description)}</DialogDescription>}
                </DialogHeader>
                <div className="space-y-2 py-2">
                    <Label htmlFor="dialogue-nom">{t(libelle)}</Label>
                    <Input
                        id="dialogue-nom"
                        value={nom}
                        maxLength={100}
                        autoFocus
                        onChange={(e) => setNom(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") {
                                e.preventDefault();
                                void envoyer();
                            }
                        }}
                    />
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => onOuvertChange(false)}>
                        {t(TEXTES.annuler)}
                    </Button>
                    <Button type="button" onClick={() => void envoyer()} disabled={!propre || enCours}>
                        {enCours ? t(TEXTES.enCours) : t(valider)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
