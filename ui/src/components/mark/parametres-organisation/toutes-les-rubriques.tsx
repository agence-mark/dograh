"use client";

/**
 * [.mark] Les écrans qui se partagent les thèmes de « Réglages de l'organisation » d'avant (U2 / U2 bis, D8), montés
 * ensemble : Entreprise (6 sous-onglets) et Réglages de l'organisation (3 thèmes). « Base et automatisations » a ses
 * propres tests (`base-client-ecran`, `apres-appel-ecran`, `page-base-et-entreprise`).
 *
 * Réservé aux tests : ils prouvent qu'AUCUN réglage n'a disparu en déplaçant les thèmes (chaque réglage de
 * l'inventaire se retrouve, se modifie et s'enregistre). `ouvrirOnglet` montre le sous-onglet qui porte un thème.
 */
import { fireEvent } from "@testing-library/react";

import { PageEntrepriseAvec } from "../entreprise/PageEntreprise";
import { PageParametresOrganisation } from "./PageParametresOrganisation";

const ONGLET_DU_THEME: Record<string, string> = {
    etablissement: "etablissements",
    equipe: "equipe",
    "rendez-vous": "rendez-vous",
    objets: "objets",
    verification: "verification",
    ecoute: "ecoute",
};

/** Montre le sous-onglet de l'écran Entreprise qui porte ce thème (sans effet pour un thème des réglages). */
export function ouvrirOnglet(theme: string) {
    const onglet = ONGLET_DU_THEME[theme];
    if (onglet) fireEvent.click(document.querySelector(`[data-onglet="${onglet}"]`) as HTMLElement);
}

export default function ToutesLesRubriques() {
    return (
        <>
            <PageEntrepriseAvec anciensThemes />
            <PageParametresOrganisation />
        </>
    );
}
