"use client";

/**
 * [.mark] K4 : une section en LIGNES EN LECTURE (libellé gris, valeur) avec un bouton « Modifier » qui ouvre la fenêtre
 * de la section (maquette `entreprise.tsx`, `SectionLue`). Les valeurs viennent de ce que l'écran sait déjà.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { useLangue } from "../langue/langue";
import { FenetreChamps, type SectionChamps, type Valeurs } from "../studio/fenetre-champs";
import { Info } from "../studio/marques";
import { TitreTableau } from "../studio/tableau";

export function LigneLue({ libelle, valeur }: { libelle: string; valeur: React.ReactNode }) {
    return (
        <div className="flex items-center gap-3 py-3 text-sm">
            <span className="w-64 shrink-0 text-muted-foreground">{libelle}</span>
            <span className="flex-1">{valeur}</span>
        </div>
    );
}

export function SectionLue({
    titre,
    info,
    lignes,
    fenetre,
    onValider,
    verifier,
}: {
    titre: string;
    info?: React.ReactNode;
    lignes: [string, React.ReactNode][];
    fenetre: { titre: string; info?: React.ReactNode; sections: SectionChamps[] };
    onValider: (valeurs: Valeurs) => void;
    verifier?: (valeurs: Valeurs) => Record<string, string> | null;
}) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    return (
        <section>
            <TitreTableau
                titre={titre}
                info={info && <Info>{info}</Info>}
                action={
                    <Button variant="outline" size="sm" onClick={() => setOuverte(true)}>
                        {t({ en: "Edit", fr: "Modifier" })}
                    </Button>
                }
            />
            <div className="mt-4 divide-y border-t">
                {lignes.map(([l, v]) => (
                    <LigneLue key={l} libelle={l} valeur={v} />
                ))}
            </div>
            <FenetreChamps
                ouverte={ouverte}
                fermer={() => setOuverte(false)}
                titre={fenetre.titre}
                info={fenetre.info}
                sections={fenetre.sections}
                valider={t({ en: "Save", fr: "Enregistrer" })}
                onValider={onValider}
                verifier={verifier}
            />
        </section>
    );
}
