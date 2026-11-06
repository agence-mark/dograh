"use client";

/**
 * [.mark] K4 : une section en LIGNES EN LECTURE (libellé gris, valeur) avec un bouton « Modifier » qui ouvre la fenêtre
 * de la section (maquette `entreprise.tsx`, `SectionLue`). Les valeurs viennent de ce que l'écran sait déjà.
 */
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import { useLangue } from "../langue/langue";
import { FenetreChamps, type RetourValidation, type SectionChamps, type Valeurs } from "../studio/fenetre-champs";
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
    onValider: (valeurs: Valeurs) => RetourValidation;
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

/**
 * [.mark] K4b : un bloc en lignes en lecture dont la fenêtre porte des CONTRÔLES DÉJÀ BRANCHÉS (`corps`) au lieu de champs
 * décrits par leurs données : les thèmes d'organisation gardent leur brouillon, leurs bornes et leur enregistrement.
 * « Enregistrer » appelle `onValider` ; « Annuler » (ou Échap) appelle `onAnnuler`, qui défait le brouillon. `action` :
 * un geste direct à côté de « Modifier » (tester, envoyer maintenant).
 */
export function BlocLu({
    id,
    titre,
    info,
    lignes,
    action,
    fenetre,
}: {
    id?: string;
    titre: string;
    info?: React.ReactNode;
    lignes: [string, React.ReactNode][];
    action?: React.ReactNode;
    fenetre?: {
        titre: string;
        info?: React.ReactNode;
        corps: React.ReactNode;
        /** Le libellé du bouton (« Enregistrer » par défaut). */
        valider?: string;
        onValider: () => RetourValidation;
        onAnnuler?: () => void;
        verifier?: () => Record<string, string> | null;
    };
}) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    const valide = useRef(false);
    return (
        <section id={id}>
            <TitreTableau
                titre={titre}
                info={info && <Info>{info}</Info>}
                action={
                    <div className="flex items-center gap-2">
                        {action}
                        {fenetre && (
                            <Button variant="outline" size="sm" onClick={() => setOuverte(true)}>
                                {t({ en: "Edit", fr: "Modifier" })}
                            </Button>
                        )}
                    </div>
                }
            />
            <div className="mt-4 divide-y border-t">
                {lignes.map(([l, v]) => (
                    <LigneLue key={l} libelle={l} valeur={v} />
                ))}
            </div>
            {fenetre && (
                <FenetreChamps
                    ouverte={ouverte}
                    fermer={() => {
                        if (!valide.current) fenetre.onAnnuler?.();
                        valide.current = false;
                        setOuverte(false);
                    }}
                    titre={fenetre.titre}
                    info={fenetre.info ?? info}
                    etroite
                    sections={[]}
                    corps={<div className="-my-5 divide-y">{fenetre.corps}</div>}
                    valider={fenetre.valider ?? t({ en: "Save", fr: "Enregistrer" })}
                    onValider={async () => {
                        valide.current = true;
                        let retour: boolean | void;
                        try {
                            retour = await fenetre.onValider();
                        } catch (e) {
                            valide.current = false;
                            throw e;
                        }
                        // Échec : la fenêtre reste ouverte, un « Annuler » défait toujours le brouillon.
                        if (retour === false) valide.current = false;
                        return retour;
                    }}
                    verifier={fenetre.verifier ? () => fenetre.verifier!() : undefined}
                />
            )}
        </section>
    );
}
