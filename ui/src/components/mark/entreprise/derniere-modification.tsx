"use client";

/**
 * [.mark] U2 bis (E56) : « modifiée par X, depuis le portail / Dograh, le … » sous chaque fiche d'établissement.
 * Lu dans le journal de la base du client (`GET /organizations/etablissements/dernieres-modifications`) : rien n'est
 * affiché pour une fiche que le journal ne connaît pas (organisation sans base rattachée, fiche jamais modifiée).
 */
import { useCallback, useEffect, useState } from "react";

import { getDernieresModificationsApiV1OrganizationsEtablissementsDernieresModificationsGet } from "@/client/sdk.gen";
import type { DerniereModification } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import { type Texte, useLangue } from "../langue/langue";

export type DernieresModifications = Record<string, DerniereModification>;

/** Lit les dernières modifications quand `actif` devient vrai (et sur demande). */
export function useDernieresModifications(actif = true) {
    const { user, loading } = useAuth();
    const [parFiche, setParFiche] = useState<DernieresModifications>({});
    const relire = useCallback(async () => {
        const reponse = await getDernieresModificationsApiV1OrganizationsEtablissementsDernieresModificationsGet();
        setParFiche(Object.fromEntries((reponse.data ?? []).map((m) => [m.id, m])));
    }, []);
    useEffect(() => {
        if (!actif || loading || !user) return;
        void relire();
    }, [actif, loading, user, relire]);
    return { parFiche, relire };
}

const ORIGINES: Record<DerniereModification["origine"], Texte> = {
    portail: { en: "from the portal", fr: "depuis le portail" },
    dograh: { en: "from Dograh", fr: "depuis Dograh" },
};

export function DerniereModificationFiche({ modification }: { modification: DerniereModification | undefined }) {
    const { t, langue } = useLangue();
    if (!modification) return null;
    const quand = new Date(modification.le).toLocaleDateString(langue === "fr" ? "fr-FR" : "en-GB", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
    });
    const qui = modification.auteur
        ? t({ en: `Last changed by ${modification.auteur}`, fr: `Modifiée en dernier par ${modification.auteur}` })
        : t({ en: "Last changed", fr: "Modifiée en dernier" });
    return (
        <span data-derniere-modification={modification.id} className="text-xs text-muted-foreground">
            {qui} {t(ORIGINES[modification.origine])}, {t({ en: "on", fr: "le" })} {quand}
        </span>
    );
}
