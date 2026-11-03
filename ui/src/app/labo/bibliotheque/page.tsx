"use client";

// [.mark] U1 : cette adresse monte l'écran actuel de la bibliothèque dans le nouveau cadre.
// U4 (E45 B) : `?famille=modeles-reglages` ouvre la rubrique Bibliothèque › Modèles de réglages (tableau, fiche, import).
import { useEffect, useState } from "react";

import PageBibliothequeDuMenu from "@/app/bibliotheque/page";
import { PageModelesDeReglages } from "@/components/mark/reglages-agent/modeles-de-reglages/PageModelesDeReglages";

export default function PageBibliothequeDuLabo() {
    const [famille, setFamille] = useState<string | null>(null);
    useEffect(() => {
        setFamille(new URLSearchParams(window.location.search).get("famille"));
    }, []);
    return famille === "modeles-reglages" ? <PageModelesDeReglages /> : <PageBibliothequeDuMenu />;
}
