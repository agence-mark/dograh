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
    repondreAUneDepenseApiV1BuilderFilsFilIdDepensesDepenseIdPost,
    reprendreUnFilApiV1BuilderFilsFilIdReprendrePost,
    suivreUnFilApiV1BuilderFilsFilIdEvenementsGet,
    type VueFil,
} from "@/client";
import { ECHEC_DU_FIL, echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { notifier } from "@/components/mark/notifications/notifier";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { appliquer, dernierMessage, type LigneDuFil, lireLesBlocs } from "./evenements";
import { STATUT_PLAFOND, STATUT_REFUSE, statutDe, TEXTES_PLAFOND } from "./plafond-du-mois";

const REPRISE_MS = 1000;

export function useFil(filId: number) {
    const { user, loading: authLoading } = useAuth();
    const [fil, setFil] = useState<VueFil | null>(null);
    const [lignes, setLignes] = useState<LigneDuFil[]>([]);
    const [erreur, setErreur] = useState<string | null>(null);
    const [relance, setRelance] = useState(0);
    const dernierId = useRef(0);
    // SE-16 : le geste refusé par le plafond du mois, à rejouer avec « continuer quand même » (jamais mémorisé au-delà de ce geste).
    const [plafond, setPlafond] = useState<null | { rejouer: () => Promise<{ error?: unknown; data?: VueFil; response?: { status?: number } }>; enCours: boolean }>(null);

    const rafraichir = useCallback(async () => {
        const r = await lireUnFilApiV1BuilderFilsFilIdGet({ path: { fil_id: filId } });
        if (r.error || !r.data) {
            setErreur(echecAffiche(r.error));
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
                        setErreur(echecAffiche(r.error));
                        return;
                    }
                    for await (const { id, evenement } of lireLesBlocs(r.data as ReadableStream<Uint8Array>)) {
                        dernierId.current = id;
                        if (evenement.type === "erreur") notifier.echec(ECHEC_DU_FIL, { erreur: evenement.message, groupe: "echec-fil" });
                        setLignes((avant) => appliquer(avant, id, evenement));
                        if (evenement.type === "depense" || evenement.type === "fin") void rafraichir();
                    }
                } catch (e) {
                    if ((e as { name?: string })?.name === "AbortError") return;
                }
                const etat = await rafraichir();
                // Une conversation recopiee de Claude Code reprend a chaque message : son flux se rouvre tant que l'ecran est la.
                if (!etat || (etat.etat !== "en_cours" && etat.genre !== "claude_code")) return;
                await new Promise((ok) => setTimeout(ok, REPRISE_MS));
            }
        })();
        return () => {
            vivant = false;
            arret.abort();
        };
    }, [authLoading, user, filId, relance, rafraichir]);

    const apres = useCallback(
        async (r: { error?: unknown; data?: VueFil; response?: { status?: number } }, rejouer?: () => Promise<{ error?: unknown; data?: VueFil; response?: { status?: number } }>) => {
            if (r.error && rejouer && statutDe(r) === STATUT_PLAFOND) {
                notifier.avertissement(TEXTES_PLAFOND.notification, { groupe: "plafond-du-mois" });
                setPlafond({ rejouer, enCours: false });
                return;
            }
            if (r.error) {
                // Jamais le texte brut du serveur à l'écran : une notification dit ce qui s'est passé (le détail va à l'équipe seule).
                notifier.echec(
                    { en: "The builder could not take this into account. Try again.", fr: "Le builder n'a pas pu le prendre en compte. Réessayez." },
                    { erreur: detailFromError(r.error, "The request failed") },
                );
                return;
            }
            setErreur(null);
            if (r.data) setFil(r.data);
            setRelance((n) => n + 1);
        },
        [],
    );

    const continuerQuandMeme = async () => {
        if (!plafond || plafond.enCours) return;
        setPlafond({ ...plafond, enCours: true });
        const r = await plafond.rejouer();
        setPlafond(null);
        if (r.error && statutDe(r) === STATUT_REFUSE) return notifier.echec(TEXTES_PLAFOND.reserve);
        await apres(r);
    };

    return {
        plafond: plafond ? { enCours: plafond.enCours } : null,
        continuerQuandMeme,
        annulerLePlafond: () => setPlafond(null),
        fil,
        lignes,
        erreur,
        enCours: fil?.etat === "en_cours",
        dernier: dernierMessage(lignes),
        envoyer: async (message: string) => {
            // `depasser_le_plafond` (SE-16) : accepté par la route ; le client généré le reçoit au prochain passage du générateur.
            const envoi = (depasser: boolean) =>
                envoyerUnMessageApiV1BuilderFilsFilIdMessagesPost({
                    path: { fil_id: filId },
                    body: (depasser ? { message, depasser_le_plafond: true } : { message }) as { message: string },
                });
            await apres(await envoi(false), () => envoi(true));
        },
        arreter: async () => apres(await arreterUnFilApiV1BuilderFilsFilIdArreterPost({ path: { fil_id: filId } })),
        rafraichir,
        repondreDepense: async (depenseId: string, accord: boolean) =>
            apres({ error: (await repondreAUneDepenseApiV1BuilderFilsFilIdDepensesDepenseIdPost({ path: { fil_id: filId, depense_id: depenseId }, body: { accord } })).error }),
        reprendre: async () => {
            const envoi = (depasser: boolean) =>
                reprendreUnFilApiV1BuilderFilsFilIdReprendrePost({
                    path: { fil_id: filId },
                    ...(depasser ? { query: { depasser_le_plafond: true } } : {}),
                } as { path: { fil_id: number } });
            await apres(await envoi(false), () => envoi(true));
        },
        modifierDernier: async (message: string) => {
            const envoi = (depasser: boolean) =>
                modifierLeDernierMessageApiV1BuilderFilsFilIdModifierDernierPost({
                    path: { fil_id: filId },
                    body: (depasser ? { message, depasser_le_plafond: true } : { message }) as { message: string },
                });
            await apres(await envoi(false), () => envoi(true));
        },
    };
}
