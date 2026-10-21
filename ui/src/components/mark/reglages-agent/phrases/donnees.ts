"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 : ce que le thème Phrases lit en dehors des réglages de l'agent.
 *
 *  - la carte (`GET /workflow/{id}/phrases/carte`, `api/services/phrases/carte.py`) : pour chaque règle, la
 *    dernière fois dite et si son étape existe encore ; pour chaque motif, la phrase en vigueur et d'où elle
 *    vient (la vue du groupe) ; pour un spécialisé, les règles du groupe héritées du principal ;
 *  - les outils de l'agent (nom, délai total essais compris) : la case « Pour l'outil » et la fin de l'attente ;
 *  - l'équipe (clés et prénoms) : la destination d'un « transférer à ».
 * Aucune de ces lectures ne bloque l'écran : une lecture qui échoue laisse la liste sans ces compléments.
 */
import { useEffect, useMemo, useState } from "react";

import { client } from "@/client/client.gen";
import { getEquipeApiV1OrganizationsEquipeGet, listToolsApiV1ToolsGet } from "@/client/sdk.gen";
import { useAuth } from "@/lib/auth";
import type { ReglePhrase } from "@/types/workflow-configurations";

import type { Texte } from "../../langue/langue";
import { delaiTotalS, lireEssais } from "../../outils/essais-outil";

export interface Dernier {
    run: number | null;
    moment: string | null;
    texte: string | null;
}

export interface MotifDeLaCarte {
    motif: string;
    famille: string;
    moment?: string;
    libelle: Texte;
    quand: Texte;
    eteinte: Texte;
    a_un_delai: boolean;
    variantes: string[];
    delai_s: number | null;
    ordre?: string | null;
    redite_s?: number | null;
    max_par_attente?: number | null;
    max_par_appel?: number | null;
    ensuite?: ReglePhrase["ensuite"] | null;
    active: boolean;
    niveau: string | null;
    etapes: Array<{ etape: string; etape_id?: string | null; variantes: string[]; delai_s: number | null; active: boolean; dernier: Dernier | null }>;
    dernier: Dernier | null;
}

/** Une règle lue par la carte, avec sa dernière fois dite et l'état de son étape. */
export type RegleDeLaCarte = ReglePhrase & { dernier?: Dernier | null; etape_supprimee?: boolean };

export interface AgentDeLaCarte {
    id: number;
    nom: string;
    est_principal: boolean;
    motifs: MotifDeLaCarte[];
    regles?: RegleDeLaCarte[];
    /** Un spécialisé : les règles « groupe » posées sur le principal. */
    regles_du_groupe?: RegleDeLaCarte[];
    lecture: Array<{ nature: string; endroit: string; texte: string }>;
}

export interface Carte {
    agents: AgentDeLaCarte[];
    actions: Array<{ fichier: string; description: string }>;
}

/** La carte de l'agent ; `version` change après un enregistrement (la dernière fois dite est relue). */
export const useCarte = (workflowId: number | undefined, actif: boolean, version: number) => {
    const { user, loading } = useAuth();
    const [carte, setCarte] = useState<Carte | null>(null);
    const [erreur, setErreur] = useState(false);
    useEffect(() => {
        if (workflowId === undefined || !actif || loading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await client.get<{ 200: Carte }, unknown, false>({
                    url: "/api/v1/workflow/{workflow_id}/phrases/carte",
                    path: { workflow_id: workflowId },
                });
                if (annule) return;
                if (reponse.error || !reponse.data) setErreur(true);
                else {
                    setErreur(false);
                    setCarte(reponse.data as Carte);
                }
            } catch {
                if (!annule) setErreur(true);
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId, actif, loading, user, version]);
    return { carte, erreur };
};

export interface OutilDeLAgent {
    uuid: string;
    nom: string;
    categorie: string;
    /** Le temps que l'outil peut durer, essais compris (outil HTTP) ; null : inconnu. */
    delaiTotalS: number | null;
}

/** Les outils d'un agent (par les identifiants portés par ses étapes). */
export const useOutilsDeLAgent = (uuids: string[], actif: boolean): OutilDeLAgent[] => {
    const { user, loading } = useAuth();
    const [outils, setOutils] = useState<OutilDeLAgent[]>([]);
    const cle = uuids.join(",");
    useEffect(() => {
        if (!actif || loading || !user || uuids.length === 0) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await listToolsApiV1ToolsGet();
                if (annule || !reponse.data) return;
                const voulus = new Set(uuids);
                setOutils(
                    (reponse.data as Array<Record<string, unknown>>)
                        .filter((o) => voulus.has(String(o.tool_uuid)))
                        .map((o) => {
                            const config = ((o.definition as Record<string, unknown> | undefined)?.config ?? {}) as Record<string, unknown>;
                            const http = String(o.category) === "http_api";
                            return {
                                uuid: String(o.tool_uuid),
                                nom: String(o.name),
                                categorie: String(o.category),
                                delaiTotalS: http ? delaiTotalS(Number(config.timeout_ms) || 5000, lireEssais(config)) : null,
                            };
                        }),
                );
            } catch {
                // La liste reste vide : une règle vise alors « tous les outils ».
            }
        })();
        return () => {
            annule = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [actif, loading, user, cle]);
    return outils;
};

export interface MembreDeLEquipe {
    cle: string;
    nom: string;
}

/** Les personnes de l'équipe de l'organisation : les destinations d'un transfert de sortie. */
export const useEquipe = (actif: boolean): MembreDeLEquipe[] => {
    const { user, loading } = useAuth();
    const [equipe, setEquipe] = useState<MembreDeLEquipe[]>([]);
    useEffect(() => {
        if (!actif || loading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await getEquipeApiV1OrganizationsEquipeGet();
                if (annule || !reponse.data) return;
                setEquipe((reponse.data.personnes ?? []).map((p) => ({ cle: p.cle, nom: [p.prenom, p.nom].filter(Boolean).join(" ") })));
            } catch {
                // Sans l'équipe lue, la destination se saisit à la main.
            }
        })();
        return () => {
            annule = true;
        };
    }, [actif, loading, user]);
    return equipe;
};

/** L'objet {clé: nom} des destinations, pour les textes de l'aperçu. */
export const useDestinations = (equipe: MembreDeLEquipe[]): Record<string, string> =>
    useMemo(() => Object.fromEntries(equipe.map((p) => [p.cle, p.nom])), [equipe]);
