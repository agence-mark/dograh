"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot F3 : la section « Cases des listes » du theme
 * « Donnees du client » (quand une base est rattachee). Trois cases que les indicateurs du portail lisent :
 * « compte comme regle seul » (issues d'appel), « opportunite » (motifs), « urgent » (degres d'urgence).
 *
 * ⛔ Aucun texte sans champ reel : chaque ligne est une valeur de liste de la base du client (libelle + code
 * en gris) et chaque interrupteur est l'une de ses trois cases. Les cases proposees pour une liste sont celles
 * que le serveur dit (`cases`), il n'y a pas de liste en dur ici. Rien n'est enregistre sans le bouton ; seules
 * les cases changees partent (une case non touchee n'est pas envoyee).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getListesValeursApiV1OrganizationsListesValeursGet,
    putListesValeursApiV1OrganizationsListesValeursPut,
} from "@/client/sdk.gen";
import type { CasesDUneValeur, ListesValeurs, ValeurDeListe } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";

/** Les cases d'une valeur, dans l'ordre d'affichage (un test les compare au client genere). */
export const CASES_LISTES_VALEURS = ["regle_seul", "opportunite", "urgent"] as const;
type Case = (typeof CASES_LISTES_VALEURS)[number];

const LIBELLE_CASE: Record<Case, Texte> = {
    regle_seul: { en: "Counts as settled alone", fr: "Compte comme réglé seul" },
    opportunite: { en: "Opportunity", fr: "Opportunité" },
    urgent: { en: "Urgent", fr: "Urgent" },
};

const cle = (liste: string, code: string) => `${liste}\u0000${code}`;

export const useListesValeurs = (actif: boolean) => {
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<ListesValeurs | null>(null);
    const [brouillon, setBrouillon] = useState<Record<string, ValeurDeListe>>({});
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    const poser = useCallback((donnees: ListesValeurs) => {
        setVue(donnees);
        const valeurs: Record<string, ValeurDeListe> = {};
        for (const l of donnees.listes ?? []) for (const v of l.valeurs ?? []) valeurs[cle(l.liste, v.code)] = v;
        setBrouillon(valeurs);
    }, []);

    useEffect(() => {
        if (!actif || authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const reponse = await getListesValeursApiV1OrganizationsListesValeursGet();
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Value lists unreadable"));
                return;
            }
            if (reponse.data) poser(reponse.data);
        })();
    }, [actif, authLoading, user, poser]);

    /** Seules les cases changees partent. */
    const changements = (): CasesDUneValeur[] => {
        const envoi: CasesDUneValeur[] = [];
        for (const l of vue?.listes ?? []) {
            for (const v of l.valeurs ?? []) {
                const apres = brouillon[cle(l.liste, v.code)];
                if (!apres) continue;
                const partie: Partial<Record<Case, boolean>> = {};
                for (const c of CASES_LISTES_VALEURS) if (Boolean(apres[c]) !== Boolean(v[c])) partie[c] = Boolean(apres[c]);
                if (Object.keys(partie).length > 0) envoi.push({ liste: l.liste, code: v.code, ...partie });
            }
        }
        return envoi;
    };
    const modifie = changements().length > 0;

    const enregistrer = async (succes: string) => {
        const valeurs = changements();
        if (valeurs.length === 0 || enCours) return;
        setEnCours(true);
        setErreur(null);
        try {
            const reponse = await putListesValeursApiV1OrganizationsListesValeursPut({ body: { valeurs } });
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "Value list boxes refused"));
                return;
            }
            poser(reponse.data);
            toast.success(succes);
        } catch {
            setErreur("Value lists: the server did not answer");
        } finally {
            setEnCours(false);
        }
    };

    const cocher = (liste: string, code: string, boite: Case, valeur: boolean) =>
        setBrouillon((avant) => ({ ...avant, [cle(liste, code)]: { ...avant[cle(liste, code)], [boite]: valeur } }));

    return { vue, brouillon, erreur, enCours, modifie, enregistrer, cocher };
};

const TITRE_SECTION: Texte = { en: "Value list boxes", fr: "Cases des listes de valeurs" };

export const SectionListesValeurs = ({ etat }: { etat: ReturnType<typeof useListesValeurs> }) => {
    const { t } = useLangue();
    const { vue, brouillon, erreur, enCours, modifie, enregistrer, cocher } = etat;

    return (
        <Intertitre
            id="donnees-listes-valeurs"
            titre={TITRE_SECTION}
            description={{
                en: "Boxes the portal's indicators read: which outcomes count as settled alone, which reasons are an opportunity, which urgency levels are urgent. None is ticked by default.",
                fr: "Les cases que lisent les indicateurs du portail : quelles issues comptent comme réglées seules, quels motifs sont une opportunité, quels degrés d'urgence sont urgents. Aucune n'est cochée d'office.",
            }}
        >
            {erreur && (
                <p className="text-sm text-destructive" role="alert" data-testid="erreur-listes-valeurs">
                    {erreur}
                </p>
            )}
            {!vue ? (
                <p className="text-sm text-muted-foreground">{t({ en: "Loading...", fr: "Chargement..." })}</p>
            ) : (
                <>
                    {(vue.listes ?? []).map((liste) => (
                        <div key={liste.liste} className="space-y-2" data-liste={liste.liste}>
                            <p className="text-sm font-medium">
                                <span className="font-mono text-xs text-muted-foreground">{liste.liste}</span>
                            </p>
                            {(liste.valeurs ?? []).length === 0 ? (
                                <p className="text-sm text-muted-foreground" data-testid={`liste-vide-${liste.liste}`}>
                                    {t({ en: "No value in this list yet.", fr: "Aucune valeur dans cette liste pour l'instant." })}
                                </p>
                            ) : (
                                (liste.valeurs ?? []).map((valeur) => (
                                    <div key={valeur.code} className="flex items-center justify-between gap-4" data-valeur={valeur.code}>
                                        <span className="text-sm">
                                            {valeur.libelle} <span className="font-mono text-xs text-muted-foreground">{valeur.code}</span>
                                        </span>
                                        <span className="flex items-center gap-4">
                                            {(liste.cases ?? []).map((boite) => (
                                                <label key={boite} className="flex items-center gap-2 text-xs" data-reglage={boite}>
                                                    <Switch
                                                        id={`liste-${liste.liste}-${valeur.code}-${boite}`}
                                                        checked={Boolean(brouillon[cle(liste.liste, valeur.code)]?.[boite])}
                                                        onCheckedChange={(v) => cocher(liste.liste, valeur.code, boite, v)}
                                                    />
                                                    {t(LIBELLE_CASE[boite])}
                                                </label>
                                            ))}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>
                    ))}
                    <Button
                        size="sm"
                        data-testid="enregistrer-listes-valeurs"
                        disabled={enCours || !modifie}
                        onClick={() => void enregistrer(t({ en: "Value list boxes saved", fr: "Cases des listes enregistrées" }))}
                    >
                        {t({ en: "Save the boxes", fr: "Enregistrer les cases" })}
                    </Button>
                </>
            )}
        </Intertitre>
    );
};
