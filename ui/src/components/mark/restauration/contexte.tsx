"use client";

/**
 * [.mark] Module Restauration, lot 12 : ce que les écrans du module partagent dans la page Entreprise.
 *
 *  - le module (allumé ou non), la liste des établissements de la base du client, l'établissement choisi dans le sélecteur ;
 *  - `useCharge` : une lecture de l'API avec son état (chargement, prêt, erreur) et « relire », sans jamais lire deux fois la même donnée.
 *
 * Aucune donnée n'est gardée ici qui ne vienne de l'API : le module est allumé quand la base du client le dit.
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";

import type { Texte } from "../langue/langue";
import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { type EtablissementDuModule, lireLeModule, poserLeModule, type Reponse } from "./donnees";

export type EtatDeLecture = "chargement" | "pret" | "erreur";

interface ValeurModule {
    etat: EtatDeLecture;
    actif: boolean;
    etablissements: EtablissementDuModule[];
    /** L'établissement choisi (identifiant), `null` tant que la liste n'est pas lue ou quand la base n'en a aucun. */
    etab: number | null;
    poserEtab: (id: number) => void;
    relire: () => Promise<void>;
    /** Allume ou retire le module ; rend vrai si la base l'a pris. */
    poser: (actif: boolean) => Promise<boolean>;
}

const Contexte = createContext<ValeurModule>({
    etat: "chargement", actif: false, etablissements: [], etab: null, poserEtab: () => undefined, relire: async () => undefined, poser: async () => false,
});
export const useModuleRestauration = () => useContext(Contexte);

export function FournisseurModuleRestauration({ children }: { children: ReactNode }) {
    const { user, loading } = useAuth();
    const [etat, setEtat] = useState<EtatDeLecture>("chargement");
    const [actif, setActif] = useState(false);
    const [etablissements, setEtablissements] = useState<EtablissementDuModule[]>([]);
    const [choisi, setChoisi] = useState<number | null>(null);

    const appliquer = useCallback((r: { actif: boolean; etablissements: EtablissementDuModule[] }) => {
        setActif(r.actif);
        setEtablissements(r.etablissements);
        setEtat("pret");
    }, []);
    const relire = useCallback(async () => {
        const r = await lireLeModule();
        if (r.error || !r.data) {
            // Une base du client non rattachée (409) n'est pas une panne : il n'y a simplement pas de module à montrer.
            setActif(false);
            setEtat("erreur");
            return;
        }
        appliquer(r.data);
    }, [appliquer]);
    const dejaLu = useRef(false);
    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [loading, user, relire]);

    const poser = useCallback(
        async (voulu: boolean) => {
            const r = await poserLeModule(voulu);
            if (r.error || !r.data) {
                echecAffiche(r.error, ECHECS.restaurationModulePoser);
                return false;
            }
            appliquer(r.data);
            return true;
        },
        [appliquer],
    );
    const etab = choisi !== null && etablissements.some((e) => e.id === choisi) ? choisi : (etablissements[0]?.id ?? null);
    const valeur = useMemo(
        () => ({ etat, actif, etablissements, etab, poserEtab: setChoisi, relire, poser }),
        [etat, actif, etablissements, etab, relire, poser],
    );
    return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

/**
 * Une lecture de l'API : `relire` la refait, `poser` remplace la donnée par ce qu'une écriture a rendu. Un changement de `cle` relit ;
 * une réponse qui arrive après un changement de clé est jetée. Une erreur dit sa phrase par `notifier` (`ECHECS`).
 */
export function useCharge<T>(charger: (() => Promise<Reponse<T>>) | null, cle: string, echec: Texte) {
    const [donnee, setDonnee] = useState<T | null>(null);
    const [etat, setEtat] = useState<EtatDeLecture>("chargement");
    const courante = useRef(cle);
    courante.current = cle;
    const chargerRef = useRef(charger);
    chargerRef.current = charger;
    const relire = useCallback(async () => {
        const f = chargerRef.current;
        if (!f) return;
        const pour = courante.current;
        const r = await f();
        if (pour !== courante.current) return;
        if (r.error || r.data === undefined) {
            setEtat("erreur");
            notifier.echec(echec, { erreur: r.error, groupe: `lecture-${echec.fr}` });
            return;
        }
        setDonnee(r.data);
        setEtat("pret");
    }, [echec]);
    useEffect(() => {
        setEtat("chargement");
        setDonnee(null);
        if (charger) void relire();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cle]);
    return { donnee, etat, relire, poser: setDonnee };
}
