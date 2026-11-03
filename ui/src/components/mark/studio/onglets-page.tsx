"use client";

/**
 * [.mark] Les sous-onglets horizontaux d'une page (Entreprise, Base et automatisations ; E56, E52).
 *
 * Même forme que les onglets de la fenêtre commune (trait sous l'onglet actif, survol en gras). L'onglet actif se
 * lit et s'écrit dans l'adresse (`?onglet=`) : un lien, un rechargement ou une ancienne adresse retombent au bon
 * endroit. Les volets restent TOUS montés (celui qui n'est pas actif est masqué, attribut `hidden`) : un brouillon non enregistré ne
 * se perd pas en changeant d'onglet. Une pastille marque l'onglet qui a un changement ou une erreur.
 */
import { type ReactNode, useEffect, useState } from "react";

import { Pastilles } from "../ecran/Theme";

export type OngletPage = { id: string; titre: string; modifie?: boolean; enErreur?: boolean; contenu: ReactNode };

const lireOnglet = () => {
    try {
        return new URLSearchParams(window.location.search).get("onglet") ?? "";
    } catch {
        return "";
    }
};

/**
 * L'onglet actif, lu dans l'adresse au montage ; choisir un onglet réécrit `?onglet=` SANS recharger ni empiler
 * l'historique (Next suit `history.replaceState`). Un onglet inconnu retombe sur `defaut`.
 */
export function useOngletDeLAdresse(ids: string[], defaut: string) {
    const [demande, setDemande] = useState("");
    useEffect(() => setDemande(lireOnglet()), []);
    const actif = ids.includes(demande) ? demande : defaut;
    const choisir = (id: string) => {
        setDemande(id);
        try {
            const adresse = new URL(window.location.href);
            adresse.searchParams.set("onglet", id);
            window.history.replaceState(window.history.state, "", adresse);
        } catch {
            /* l'onglet reste choisi à l'écran */
        }
    };
    return { actif, choisir };
}

export function OngletsPage({ onglets, defaut }: { onglets: OngletPage[]; defaut?: string }) {
    const { actif, choisir } = useOngletDeLAdresse(
        onglets.map((o) => o.id),
        defaut ?? onglets[0].id,
    );
    return (
        <div className="space-y-6">
            <div role="tablist" className="flex flex-wrap items-center gap-1 border-b">
                {onglets.map((o) => (
                    <button
                        key={o.id}
                        type="button"
                        role="tab"
                        id={`onglet-${o.id}`}
                        aria-selected={actif === o.id}
                        aria-controls={`volet-${o.id}`}
                        data-onglet={o.id}
                        onClick={() => choisir(o.id)}
                        className={`-mb-px flex cursor-pointer items-center gap-2 border-b-2 px-3 py-2.5 text-sm ${
                            actif === o.id
                                ? "border-primary font-medium"
                                : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"
                        }`}
                    >
                        {o.titre}
                        <Pastilles modifie={Boolean(o.modifie)} enErreur={Boolean(o.enErreur)} />
                    </button>
                ))}
            </div>
            {onglets.map((o) => (
                <div key={o.id} role="tabpanel" id={`volet-${o.id}`} aria-labelledby={`onglet-${o.id}`} hidden={actif !== o.id}>
                    {o.contenu}
                </div>
            ))}
        </div>
    );
}
