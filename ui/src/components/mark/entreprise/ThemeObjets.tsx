"use client";

/**
 * [.mark] U2 bis (E56) : le sous-onglet « Objets ». La section est celle du thème « Établissements » d'avant
 * (`SectionObjets`, qui porte déjà son titre et s'enregistre seule : objets et plafond dans la base du client).
 */
import { useResumeEtablissements } from "../parametres-organisation/ModaleEtablissements";
import { SectionObjets } from "../parametres-organisation/SectionObjets";

export const ThemeObjets = () => {
    const etablissements = useResumeEtablissements();
    return (
        <section data-theme="objets">
            <SectionObjets etablissements={(etablissements.liste ?? []).map((e) => ({ id: e.id, nom: e.nom }))} />
        </section>
    );
};
