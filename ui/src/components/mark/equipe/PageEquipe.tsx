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
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { useAuth } from "@/lib/auth";

import { VueJournal } from "./VueJournal";
import { VueMembres } from "./VueMembres";
import { VueRoles } from "./VueRoles";

type Onglet = "membres" | "roles" | "journal";

export function PageEquipe() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [onglet, setOnglet] = useState<Onglet>("membres");
    const [droits, setDroits] = useState<string[] | null>(null);

    useEffect(() => {
        if (loading || !user) return;
        monProfilApiV1EquipeMarkMoiGet().then((res) => setDroits(res.data?.permissions ?? []));
    }, [loading, user]);

    const noms: Record<Onglet, string> = {
        membres: t({ en: "Members", fr: "Membres" }),
        roles: t({ en: "Roles", fr: "Rôles" }),
        journal: t({ en: "Journal", fr: "Journal" }),
    };

    if (droits === null) return <div className="mx-auto w-full max-w-5xl p-6"><EtatVide cas="chargement" /></div>;
    if (!droits.includes("equipe.gerer")) {
        return (
            <div className="mx-auto w-full max-w-5xl p-6">
                <EtatVide cas="acces" role={t({ en: "Manage members", fr: "Gérer les membres" })} />
            </div>
        );
    }

    return (
        <div className="mx-auto w-full max-w-5xl space-y-6 p-6">
            <TitrePage
                titre={t({ en: "Team and roles", fr: "Équipe et rôles" })}
                info={t({
                    en: "Members join by invitation. A role sets the spaces a member opens and what they can do. Every change is written to the journal.",
                    fr: "On rejoint l'équipe sur invitation. Un rôle fixe les espaces qu'un membre ouvre et ce qu'il peut faire. Chaque geste est écrit au journal.",
                })}
            />
            <Segmente
                valeur={noms[onglet]}
                options={Object.values(noms)}
                changer={(v) => setOnglet((Object.keys(noms) as Onglet[]).find((k) => noms[k] === v) ?? "membres")}
            />
            {onglet === "membres" && <VueMembres />}
            {onglet === "roles" && <VueRoles peutGerer={droits.includes("roles.gerer")} />}
            {onglet === "journal" && <VueJournal />}
        </div>
    );
}

