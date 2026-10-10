"use client";

/**
 * [.mark] The connectors' catalogue and THIS organization's connections (chantier
 * l-agent-travaille, L5; plan connecteurs-agent D6). The server scopes both to the signed-in
 * user's organization: nothing here names an organization.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
    getCatalogueApiV1ConnecteursCatalogueGet,
    getConnexionsApiV1ConnecteursConnexionsGet,
    postLienApiV1ConnecteursLienPost,
} from "@/client/sdk.gen";
import type { ConnecteurVue, EtatConnexions, IntegrationToolConfig } from "@/client/types.gen";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

export type ConfigIntegration = IntegrationToolConfig;

export const DELAI_DEFAUT_MS = 5000;
// Lot D d'agent-leger-greffier : mirrors of `api/schemas/tool.py` (IntegrationToolConfig).
export const SEUIL_PATIENCE_DEFAUT_MS = 1200;
export const ATTENTE_MAX_DEFAUT_MS = 2500;

/** The definition of a new integration tool: the first action of the catalogue, its defaults. */
export const configParDefaut = (catalogue: ConnecteurVue[], connecteur?: string, action?: string): ConfigIntegration | null => {
    const c = catalogue.find((x) => x.nom === connecteur) ?? catalogue[0];
    const a = c?.actions.find((x) => x.nom === action) ?? c?.actions[0];
    if (!c || !a) return null;
    return {
        connecteur: c.nom,
        action: a.nom,
        reglages: { ...a.reglages_par_defaut },
        delai_ms: DELAI_DEFAUT_MS,
        phrase_attente: null,
        phrase_repli: null,
        anticipable: false,
        declencheurs: {},
        seuil_patience_ms: SEUIL_PATIENCE_DEFAUT_MS,
        champs_requis: [],
        attente_max_ms: ATTENTE_MAX_DEFAUT_MS,
    };
};

export const useConnecteurs = () => {
    const { user, loading: authLoading } = useAuth();
    const [catalogue, setCatalogue] = useState<ConnecteurVue[] | null>(null);
    const [etat, setEtat] = useState<EtatConnexions | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const dejaLu = useRef(false);

    const relire = useCallback(async () => {
        let c, e;
        try {
            [c, e] = await Promise.all([getCatalogueApiV1ConnecteursCatalogueGet(), getConnexionsApiV1ConnecteursConnexionsGet()]);
        } catch {
            setErreur("Connector catalogue unreachable");
            return;
        }
        if (c.error || !c.data) {
            setErreur(detailFromError(c.error, "Connector catalogue unreadable"));
            return;
        }
        setErreur(null);
        setCatalogue(c.data);
        setEtat(e.data ?? { nango_configure: false, connexions: [], erreur: detailFromError(e.error, "Connections unreadable") });
    }, []);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);

    const demanderLien = useCallback(async (connecteurs: string[]) => {
        const r = await postLienApiV1ConnecteursLienPost({ body: { connecteurs } });
        if (r.error || !r.data) throw new Error(detailFromError(r.error, "No authorization link"));
        return r.data;
    }, []);

    return { catalogue, etat, erreur, relire, demanderLien };
};

export type Connecteurs = ReturnType<typeof useConnecteurs>;
