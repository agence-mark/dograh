"use client";

import { type ReactNode, useLayoutEffect } from "react";
import { createPortal } from "react-dom";

import { LARGEUR_DEFAUT, usePanneau } from "./panneau-droit";

/**
 * Un contenu qui vit comme un ONGLET du panneau unique de droite (clôture D1, É29/É30) : le builder et l'essai de l'agent n'ont plus
 * de panneau flottant à eux. L'onglet s'inscrit tant que le contenu est monté et se retire à son démontage ; le contenu reste monté
 * (donc sa conversation, son essai en cours) même quand un autre onglet est devant.
 * Sans panneau (un test, un composant seul), rien n'est rendu ici : l'appelant garde son repli.
 */
export function OngletDuPanneau({ id, titre, fermer, largeur = LARGEUR_DEFAUT, children }: { id: string; titre: string; fermer: () => void; largeur?: number; children: ReactNode }) {
    const panneau = usePanneau();
    const inscrire = panneau?.inscrire;
    const retirer = panneau?.retirer;
    const majTitre = panneau?.majTitre;
    useLayoutEffect(() => {
        if (!inscrire || !retirer) return;
        inscrire({ id, titre, apercu: false, fermer, largeur });
        return () => retirer(id);
        // `titre` suit par `majTitre` : changer de langue ne doit pas rouvrir l'onglet.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, inscrire, retirer, largeur]);
    useLayoutEffect(() => {
        majTitre?.(id, titre);
    }, [id, titre, majTitre]);
    if (!panneau?.corps) return null;
    return createPortal(
        <div data-onglet-panneau={id} hidden={panneau.actif !== id} className="h-full min-h-0">
            {children}
        </div>,
        panneau.corps,
    );
}
