"use client";

import { EtatVide } from "@/components/mark/studio/etat-vide";

/**
 * [.mark] L (fluidité) : l'état de chargement d'un changement de page. Il est montré à l'instant du clic, dans la
 * zone centrale du cadre (le menu reste), jamais un écran blanc ; il est aussi la partie de la page que Next précharge
 * avec les liens visibles, donc la page voisine répond avant même que son code soit arrivé.
 */
export default function Loading() {
  return (
    <div className="p-6">
      <EtatVide cas="chargement" lignes={6} />
    </div>
  );
}
