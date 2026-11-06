"use client";

/**
 * [.mark] C4 : UNE lecture des établissements par page.
 *
 * L'écran « Entreprise » lisait `GET /organizations/etablissements` quatre fois (onglet Établissements, Équipe, Rendez-vous,
 * Variables), à des instants différents : le partage des lectures en vol (lot L) n'attrape que les lectures simultanées. Le
 * fournisseur lit la liste une fois, la garde, et la relit sur demande (après une écriture) ; les onglets la lisent ici.
 * `useResumeEtablissements` s'en sert quand un fournisseur existe, sinon lit pour son propre compte (autres écrans).
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { getEtablissementsApiV1OrganizationsEtablissementsGet } from "@/client/sdk.gen";
import type { Etablissement } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

export interface EtablissementsLus {
    liste: Etablissement[] | null;
    illisible: boolean;
    relire: () => Promise<void>;
}

const Contexte = createContext<EtablissementsLus | null>(null);

/** Lit la liste une fois l'authentification prête (si `actif`), la relit sur demande. */
export function useLireEtablissements(actif = true): EtablissementsLus {
    const { user, loading: authLoading } = useAuth();
    const [liste, setListe] = useState<Etablissement[] | null>(null);
    const [illisible, setIllisible] = useState(false);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getEtablissementsApiV1OrganizationsEtablissementsGet();
        setIllisible(Boolean(reponse.error));
        setListe(reponse.data?.etablissements ?? (reponse.error ? null : []));
    }, []);
    // `pret` (un booléen) et non `user` : l'objet utilisateur change d'identité sans que rien ait changé.
    const pret = !authLoading && Boolean(user);
    useEffect(() => {
        if (!actif || !pret || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [actif, pret, relire]);
    return { liste, illisible, relire };
}

export function FournisseurEtablissements({ children }: { children: React.ReactNode }) {
    const lus = useLireEtablissements();
    return <Contexte.Provider value={lus}>{children}</Contexte.Provider>;
}

/** Les établissements partagés de la page, ou `null` hors d'un fournisseur. */
export function useEtablissementsPartages(): EtablissementsLus | null {
    return useContext(Contexte);
}
