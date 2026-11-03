"use client";

/**
 * [.mark] Réglages › Équipe et rôles (U2 ter, E59) : Membres, Rôles, Journal. Tout vient de `/equipe-mark/*` :
 * rien n'est affiché qui n'existe pas côté serveur, les droits sont vérifiés par le serveur (un compte sans
 * `equipe.gerer` voit l'état « accès »), et chaque liste est paginée côté serveur (25 par page).
 */
import { useEffect, useState } from "react";

import { monProfilApiV1EquipeMarkMoiGet } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Info } from "@/components/mark/studio/marques";
import { TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

import { VueJournal } from "./VueJournal";
import { VueMembres } from "./VueMembres";
import { VueRoles } from "./VueRoles";

/** L'onglet « Équipe et rôles » de Réglages (forme de la maquette) : Membres, Rôles, puis le Journal dans sa fenêtre. */
export function EquipeEtRoles() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [droits, setDroits] = useState<string[] | null>(null);
    const [journal, setJournal] = useState(false);

    useEffect(() => {
        if (loading || !user) return;
        monProfilApiV1EquipeMarkMoiGet().then((res) => setDroits(res.data?.permissions ?? []));
    }, [loading, user]);

    if (droits === null) return <EtatVide cas="chargement" />;
    if (!droits.includes("equipe.gerer")) return <EtatVide cas="acces" role={t({ en: "Manage members", fr: "Gérer les membres" })} />;

    return (
        <div className="space-y-6">
            <VueMembres />
            <VueRoles peutGerer={droits.includes("roles.gerer")} />
            <TitreTableau
                titre={t({ en: "Journal", fr: "Journal" })}
                info={
                    <Info>
                        {t({
                            en: "Who changed what, in which space: agents, publications, settings, team and roles. Every gesture is written.",
                            fr: "Qui a modifié quoi, dans quel espace : agents, publications, réglages, équipe et rôles. Chaque geste est écrit.",
                        })}
                    </Info>
                }
                action={
                    <Button variant="outline" size="sm" onClick={() => setJournal(true)}>
                        {t({ en: "View", fr: "Consulter" })}
                    </Button>
                }
            />
            <FenetreChamps
                ouverte={journal}
                fermer={() => setJournal(false)}
                titre={t({ en: "Journal", fr: "Journal" })}
                info={t({
                    en: "All the actions of the team, the most recent first. Nothing is erased: a cancelled action is a new line.",
                    fr: "Toutes les actions de l'équipe, la plus récente d'abord. Rien ne s'efface : une action annulée est une nouvelle ligne.",
                })}
                valider={t({ en: "Close", fr: "Fermer" })}
                sections={[]}
                corps={<VueJournal />}
            />
        </div>
    );
}
