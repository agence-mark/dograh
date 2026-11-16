"use client";

/**
 * [.mark] Module Restauration, lot 19 (M44, F13) : le groupe « Module Restauration » de Réglages de l'agent › Modules.
 *
 * Le serveur rend le module d'ensemble `restauration` (`api/services/modules/registre.py`, `RESTAURATION`) avec ce qu'il lui faut (le classeur
 * de l'établissement) ; il ne porte pas d'interrupteur à lui : il est allumé par les outils de ses connecteurs sur une étape. Le groupe n'est
 * montré que module allumé pour l'organisation (la même lecture que la page Entreprise). Une ligne par pièce du module, avec ce que fait la pièce,
 * le kit d'outils qui la porte (lu dans la bibliothèque des Outils) et, au niveau du groupe, ce sur quoi le module se branche (lu au serveur).
 * La commande et la recherche dans une liste ont leur propre sous-menu (interrupteur et réglages), juste dessous.
 */
import { Puzzle } from "lucide-react";
import { useEffect, useState } from "react";

import type { ModuleDeLAgent } from "@/client/types.gen";

import { type Texte, useLangue } from "../langue/langue";
import { type Kit, lireLesKits } from "../outils/donnees-outils";
import { Besoins, ETAT, SousMenuModule } from "../reglages-agent/sous-menu-module";
import { Info } from "../studio/marques";
import { lireLeModule } from "./donnees";

interface PieceDuModule {
    code: string;
    titre: Texte;
    aide: Texte;
    /** Le nom du kit livré qui porte ses outils (`api/services/outils_mark/kits_livres.py`). */
    kit: string;
    /** Éteinte tant que l'établissement ne l'allume pas : le dire. */
    eteinte?: Texte;
}

const PIECES: PieceDuModule[] = [
    {
        code: "reservation",
        titre: { en: "Booking", fr: "Réservation" },
        aide: {
            en: "Looks for a free table by seats and slot, then books, changes or cancels it according to the capacity.",
            fr: "Cherche une table libre selon les couverts et le créneau, puis réserve, modifie ou annule selon la capacité.",
        },
        kit: "Réservation",
    },
    {
        code: "envois",
        titre: { en: "Sending", fr: "Envois" },
        aide: {
            en: "Sends a message to the caller (menu, confirmation, review request). Texts and triggers are set in the restaurant settings.",
            fr: "Envoie un message à l'appelant (carte, confirmation, demande d'avis). Les textes et les déclencheurs se règlent dans les réglages du restaurant.",
        },
        kit: "Envois",
        eteinte: { en: "Off until the place switches it on.", fr: "Éteint tant que le lieu ne l'allume pas." },
    },
];

export const GroupeModuleRestauration = ({ module }: { module: ModuleDeLAgent | undefined }) => {
    const { t } = useLangue();
    const [actifOrganisation, setActifOrganisation] = useState(false);
    const [kits, setKits] = useState<Kit[]>([]);
    const [ouverts, setOuverts] = useState<Set<string>>(() => new Set());

    // Deux lectures indépendantes, en parallèle ; sans elles le groupe reste simplement caché (les réglages n'en dépendent pas).
    useEffect(() => {
        let annule = false;
        (async () => {
            const [etat, bibliotheque] = await Promise.all([lireLeModule().catch(() => null), lireLesKits().catch(() => null)]);
            if (annule) return;
            setActifOrganisation(Boolean(etat?.data?.actif));
            setKits(bibliotheque?.data ?? []);
        })();
        return () => {
            annule = true;
        };
    }, []);

    if (!module || !actifOrganisation) return null;
    const allume = Boolean(module.actif);
    const basculer = (code: string) =>
        setOuverts((avant) => {
            const apres = new Set(avant);
            if (apres.has(code)) apres.delete(code);
            else apres.add(code);
            return apres;
        });

    return (
        <section className="space-y-3" data-groupe-module="restauration">
            <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <Puzzle className="size-3.5" />
                {t({ en: "Restaurant module", fr: "Module Restauration" })}
                <span className="normal-case tracking-normal">{t(allume ? ETAT.on : ETAT.off)}</span>
                <Info>
                    {t({
                        en: "Added by the company's Restaurant module: each line says what it does, the tool kit that carries it, and what the module plugs into. It is on as soon as a published step carries one of its tools.",
                        fr: "Ajoutées par le module Restauration de l'entreprise : chaque ligne dit ce qu'elle fait et le kit d'outils qui la porte, puis ce sur quoi le module se branche. Il est allumé dès qu'une étape publiée porte un de ses outils.",
                    })}
                </Info>
            </p>
            {PIECES.map((piece) => {
                const kit = kits.find((k) => k.name === piece.kit);
                return (
                    <SousMenuModule
                        key={piece.code}
                        ensemble
                        module={{ code: piece.code, titre: piece.titre, interrupteur: null, reglages: [] }}
                        allume={null}
                        ouvert={ouverts.has(piece.code)}
                        onBasculer={() => basculer(piece.code)}
                    >
                        <p className="text-xs text-muted-foreground">{t(piece.aide)}</p>
                        {piece.eteinte && <p className="text-xs text-muted-foreground">{t(piece.eteinte)}</p>}
                        <p className="text-xs text-muted-foreground" data-kit-du-module={piece.code}>
                            {t({ en: "Tool kit:", fr: "Kit d'outils :" })}{" "}
                            <b className="font-medium text-foreground">{kit ? kit.name : t({ en: "not installed", fr: "non installé" })}</b>
                            {kit && (
                                <>
                                    {" "}
                                    · {kit.items.length} {t({ en: "tools", fr: "outils" })}
                                </>
                            )}
                        </p>
                    </SousMenuModule>
                );
            })}
            <Besoins module={module} />
        </section>
    );
};
