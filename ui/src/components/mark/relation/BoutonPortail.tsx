"use client";

/**
 * [.mark] « Ouvrir son portail » : un lien d'une minute, à usage unique, créé par `POST /relation/clients/<org>/entree`. Sans adresse de portail
 * réglée (`NEXT_PUBLIC_PORTAIL_URL`, variable du déploiement), le geste dit pourquoi au lieu de ne rien faire.
 * Clôture D2 (É15, É16) : un seul geste pour la fiche Relation, l'accueil du client (bouton plein de la barre du haut) et la barre latérale du client.
 */
import { DoorOpen } from "lucide-react";
import { useState } from "react";

import { ouvrirSonPortailApiV1RelationClientsOrganizationIdEntreePost } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";

import { ADRESSE_PORTAIL, lienDEntree } from "./commun";

export function useOuvrirSonPortail(organisation: number) {
    const [envoi, setEnvoi] = useState(false);
    const ouvrir = async () => {
        setEnvoi(true);
        const res = await ouvrirSonPortailApiV1RelationClientsOrganizationIdEntreePost({ path: { organization_id: organisation }, body: {} });
        setEnvoi(false);
        if (!res.data) return notifier.echec({ fr: "Lien non créé. Réessayez.", en: "Link not created. Try again." }, { erreur: res.error });
        window.open(lienDEntree(res.data.lien), "_blank", "noopener");
    };
    return { ouvrir, envoi, disponible: Boolean(ADRESSE_PORTAIL) };
}

export const RAISON_SANS_PORTAIL = {
    en: "The portal address is not set (NEXT_PUBLIC_PORTAIL_URL).",
    fr: "L'adresse du portail n'est pas réglée (NEXT_PUBLIC_PORTAIL_URL).",
};

export function BoutonPortail({ organisation }: { organisation: number }) {
    const { t } = useLangue();
    const { ouvrir, envoi, disponible } = useOuvrirSonPortail(organisation);
    return (
        <span className="inline-flex items-center gap-1">
            <Button size="sm" className="cursor-pointer" disabled={!disponible || envoi} onClick={() => void ouvrir()}>
                <DoorOpen className="size-4" /> {t({ en: "Open its portal", fr: "Ouvrir son portail" })}
            </Button>
            {!disponible && <Info>{t(RAISON_SANS_PORTAIL)}</Info>}
        </span>
    );
}
