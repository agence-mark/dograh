"use client";

/**
 * [.mark] The calendar software of the hub (chantier l-agent-collegue, L4, H2, H8), theme
 * « Integrations ».
 *
 * A drop-down menu of the declared translators (Google Agenda, Microsoft Outlook…), the state of
 * this organization's connection to the one chosen, and its authorization link. The planner books
 * in the software chosen here; nothing chosen = no calendar software, the planner is off (X2).
 * Acts at once with its own button, like the connections above it (E6, exceptions of the theme).
 * The organization is never chosen here: the server takes the signed-in user's (D6).
 */
import { Link2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getChoixTraducteursApiV1ConnecteursTraducteursChoixGet,
    getTraducteursApiV1ConnecteursTraducteursGet,
    putChoixTraducteursApiV1ConnecteursTraducteursChoixPut,
} from "@/client/sdk.gen";
import type { TraducteurVue } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampReglage } from "../ecran/ChampReglage";
import { useLangue } from "../langue/langue";
import type { Connecteurs } from "./useConnecteurs";

const AUCUN = "";

export function BlocTraducteurs({ connecteurs }: { connecteurs: Connecteurs }) {
    const { t } = useLangue();
    const [traducteurs, setTraducteurs] = useState<TraducteurVue[] | null>(null);
    const [enregistre, setEnregistre] = useState<string>(AUCUN);
    const [choix, setChoix] = useState<string>(AUCUN);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [lien, setLien] = useState<string | null>(null);
    const { user, loading: authLoading } = useAuth();
    const dejaLu = useRef(false);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const [liste, choisi] = await Promise.all([
                getTraducteursApiV1ConnecteursTraducteursGet(),
                getChoixTraducteursApiV1ConnecteursTraducteursChoixGet(),
            ]);
            if (liste.error || !liste.data) {
                setErreur(detailFromError(liste.error, "Calendar software unreadable"));
                return;
            }
            setTraducteurs(liste.data.filter((x) => x.domaine === "agenda"));
            setEnregistre(choisi.data?.agenda ?? AUCUN);
            setChoix(choisi.data?.agenda ?? AUCUN);
        })();
    }, [authLoading, user]);

    if (traducteurs === null) return erreur ? <p className="text-sm text-destructive">{erreur}</p> : null;

    const choisi = traducteurs.find((x) => x.systeme === choix) ?? null;
    const connexion = choisi
        ? (connecteurs.etat?.connexions ?? []).find((c) => c.integration === choisi.integration)
        : undefined;

    const enregistrer = async () => {
        setEnCours(true);
        setErreur(null);
        const r = await putChoixTraducteursApiV1ConnecteursTraducteursChoixPut({ body: { agenda: choix || null } });
        setEnCours(false);
        if (r.error) {
            setErreur(detailFromError(r.error, "Calendar software not saved"));
            return;
        }
        setEnregistre(choix);
        toast.success(t({ en: "Calendar software saved", fr: "Logiciel d'agenda enregistré" }));
    };

    const genererLien = async () => {
        if (!choisi) return;
        try {
            const r = await connecteurs.demanderLien([choisi.systeme]);
            setLien(r.lien ?? null);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : t({ en: "No authorization link", fr: "Pas de lien d'autorisation" }));
        }
    };

    return (
        <div className="space-y-2" id="bloc-traducteurs" data-testid="bloc-traducteurs">
            <ChampReglage
                cle="agenda"
                idControle="traducteur-agenda"
                libelle={{ en: "Calendar software of the agent", fr: "Logiciel d'agenda de l'agent" }}
                aides={[
                    {
                        en: "The planner reads the team's agendas and books appointments in this software, one agenda per person (« Team and routing »). None: the planner is off.",
                        fr: "Le planificateur lit les agendas de l'équipe et pose les rendez-vous dans ce logiciel, un agenda par personne (« Équipe et routage »). Aucun : le planificateur est éteint.",
                    },
                ]}
            >
                <select
                    id="traducteur-agenda"
                    className="rounded border border-border bg-background px-2 py-1 text-sm"
                    value={choix}
                    onChange={(e) => {
                        setChoix(e.target.value);
                        setLien(null);
                    }}
                >
                    <option value={AUCUN}>{t({ en: "None", fr: "Aucun" })}</option>
                    {traducteurs.map((x) => (
                        <option key={x.systeme} value={x.systeme}>
                            {x.libelle}
                        </option>
                    ))}
                </select>
            </ChampReglage>
            {choisi && connecteurs.etat?.nango_configure && (
                <div className="flex flex-wrap items-center gap-3 rounded-md border bg-(--surface) p-3 text-sm" data-testid="etat-traducteur">
                    <span className="font-medium">{choisi.libelle}</span>
                    {connexion ? (
                        <span className="text-(--signal-ok)">{t({ en: "Connected", fr: "Connecté" })}</span>
                    ) : (
                        <span className="text-(--signal-warn)">{t({ en: "Not connected", fr: "Non connecté" })}</span>
                    )}
                    <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={() => void genererLien()}>
                        <Link2 className="mr-2 h-3.5 w-3.5" />
                        {connexion
                            ? t({ en: "New authorization link", fr: "Nouveau lien d'autorisation" })
                            : t({ en: "Authorization link for the client", fr: "Lien d'autorisation pour le client" })}
                    </Button>
                    {lien && <Input readOnly value={lien} id="lien-autorisation-traducteur" className="w-full font-mono text-xs" />}
                </div>
            )}
            {choisi && connecteurs.etat && !connecteurs.etat.nango_configure && (
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "No Nango on this installation: the planner cannot reach the agendas.",
                        fr: "Pas de Nango sur cette installation : le planificateur ne peut pas lire les agendas.",
                    })}
                </p>
            )}
            {erreur && (
                <p className="text-sm text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            <Button type="button" size="sm" disabled={enCours || choix === enregistre} onClick={() => void enregistrer()} data-testid="enregistrer-traducteur">
                {t({ en: "Save the calendar software", fr: "Enregistrer le logiciel d'agenda" })}
            </Button>
        </div>
    );
}
