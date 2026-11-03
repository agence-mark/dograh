"use client";

import { type Texte, useLangue } from "../../langue/langue";
import { Marque, type TonMarque } from "../../studio/marques";

/** Le statut d'un modèle est celui de la version courante de son élément de bibliothèque (E19 : une seule forme de badge). */
const STATUTS: Record<string, { ton: TonMarque; texte: Texte }> = {
    candidat: { ton: "neutre", texte: { en: "Candidate", fr: "Candidat" } },
    recette: { ton: "succes", texte: { en: "Proven", fr: "Recette" } },
    rejete: { ton: "danger", texte: { en: "Rejected", fr: "Rejeté" } },
};

export const MarqueStatut = ({ statut }: { statut: string }) => {
    const { t } = useLangue();
    const s = STATUTS[statut] ?? STATUTS.candidat;
    return <Marque ton={s.ton}>{t(s.texte)}</Marque>;
};
