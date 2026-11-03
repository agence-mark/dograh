"use client";

/**
 * [.mark] builder partie 2, U5 : une conversation du builder côté écran. Elle lit son état, rejoue ses événements depuis le
 * début (ou depuis le dernier reçu), puis suit le direct. Fermer ou recharger l'onglet n'arrête rien : le travail tourne sur le
 * serveur, l'écran se rebranche et reprend à l'identifiant du dernier événement reçu.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
    arreterUnFilApiV1BuilderFilsFilIdArreterPost,
    envoyerUnMessageApiV1BuilderFilsFilIdMessagesPost,
    lireUnFilApiV1BuilderFilsFilIdGet,
    modifierLeDernierMessageApiV1BuilderFilsFilIdModifierDernierPost,
    reprendreUnFilApiV1BuilderFilsFilIdReprendrePost,
    suivreUnFilApiV1BuilderFilsFilIdEvenementsGet,
    type VueFil,
} from "@/client";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { appliquer, dernierMessage, type LigneDuFil, lireLesBlocs } from "./evenements";

const REPRISE_MS = 1000;

export function useFil(filId: number) {
    const { user, loading: authLoading } = useAuth();
    const [fil, setFil] = useState<VueFil | null>(null);
    const [lignes, setLignes] = useState<LigneDuFil[]>([]);
    const [erreur, setErreur] = useState<string | null>(null);
    const [relance, setRelance] = useState(0);
    const dernierId = useRef(0);

    const rafraichir = useCallback(async () => {
        const r = await lireUnFilApiV1BuilderFilsFilIdGet({ path: { fil_id: filId } });
        if (r.error || !r.data) {
            setErreur(detailFromError(r.error, "Conversation not found"));
            return null;
        }
        setFil(r.data);
        return r.data;
    }, [filId]);

    useEffect(() => {
        if (authLoading || !user) return;
        dernierId.current = 0;
        setLignes([]);
        void rafraichir();
    }, [authLoading, user, filId, rafraichir]);

    // Le flux : rejoué depuis le dernier reçu, rouvert tant que le travail n'est pas fini (coupure réseau comprise).
    useEffect(() => {
        if (authLoading || !user) return;
        const arret = new AbortController();
        let vivant = true;
        (async () => {
            while (vivant) {
                try {
                    const r = await suivreUnFilApiV1BuilderFilsFilIdEvenementsGet({
                        path: { fil_id: filId },
                        query: { depuis: dernierId.current },
                        parseAs: "stream",
                        signal: arret.signal,
                    });
                    if (r.error || !r.data) {
                        setErreur(detailFromError(r.error, "The conversation could not be read"));
                        return;
                    }
                    for await (const { id, evenement } of lireLesBlocs(r.data as ReadableStream<Uint8Array>)) {
                        dernierId.current = id;
                        setLignes((avant) => appliquer(avant, id, evenement));
                        if (evenement.type === "depense" || evenement.type === "fin") void rafraichir();
                    }
                } catch (e) {
                    if ((e as { name?: string })?.name === "AbortError") return;
                }
                const etat = await rafraichir();
                if (!etat || etat.etat !== "en_cours") return;
                await new Promise((ok) => setTimeout(ok, REPRISE_MS));
            }
        })();
        return () => {
            vivant = false;
            arret.abort();
        };
    }, [authLoading, user, filId, relance, rafraichir]);

    const apres = useCallback(
        async (r: { error?: unknown; data?: VueFil }) => {
            if (r.error) {
                setErreur(detailFromError(r.error, "The request failed"));
                return;
            }
            setErreur(null);
            if (r.data) setFil(r.data);
            setRelance((n) => n + 1);
        },
        [],
    );

    return {
        fil,
        lignes,
        erreur,
        enCours: fil?.etat === "en_cours",
        dernier: dernierMessage(lignes),
        envoyer: async (message: string) =>
            apres(await envoyerUnMessageApiV1BuilderFilsFilIdMessagesPost({ path: { fil_id: filId }, body: { message } })),
        arreter: async () => apres(await arreterUnFilApiV1BuilderFilsFilIdArreterPost({ path: { fil_id: filId } })),
        reprendre: async () => apres(await reprendreUnFilApiV1BuilderFilsFilIdReprendrePost({ path: { fil_id: filId } })),
        modifierDernier: async (message: string) =>
            apres(await modifierLeDernierMessageApiV1BuilderFilsFilIdModifierDernierPost({ path: { fil_id: filId }, body: { message } })),
    };
}
