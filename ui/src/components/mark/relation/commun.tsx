"use client";

import { useCallback, useEffect, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Marque, PointEtat, type TonMarque } from "@/components/mark/studio/marques";
import { useAuth } from "@/lib/auth";
import { useLogoEspace } from "@/lib/logos-espaces";

/**
 * [.mark] Hub « Relation clients » (U3 septies, E78) : libellés et petits outils communs aux écrans.
 * Les états viennent du serveur (`/relation/*`) ; rien n'est affiché qui n'y existe pas.
 */
export const ETATS_FIL: Record<string, { texte: Texte; ton: TonMarque }> = {
    nouveau: { texte: { en: "New", fr: "Nouveau" }, ton: "plein" },
    en_cours: { texte: { en: "In progress", fr: "En cours" }, ton: "attention" },
    repondu: { texte: { en: "Answered", fr: "Répondu" }, ton: "succes" },
    clos: { texte: { en: "Closed", fr: "Clos" }, ton: "neutre" },
};

export const ETATS_DEMANDE: Record<string, Texte> = {
    nouvelle: { en: "New request", fr: "Nouvelle" },
    proposee: { en: "Proposed", fr: "Proposée" },
    a_coder: { en: "To build", fr: "À coder" },
    refusee: { en: "Declined", fr: "Refusée" },
};

export function MarqueEtat({ etat }: { etat: string }) {
    const { t } = useLangue();
    const e = ETATS_FIL[etat];
    return <Marque ton={e?.ton ?? "neutre"}>{e ? t(e.texte) : etat}</Marque>;
}

/** Date lisible : l'heure pour aujourd'hui, sinon jour et mois. */
export function quand(iso: string | null | undefined): string {
    if (!iso) return "";
    const d = new Date(iso);
    const auj = new Date();
    return d.toDateString() === auj.toDateString()
        ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString([], { day: "2-digit", month: "2-digit" }) +
              " " +
              d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Charge une liste à l'ouverture et à la demande ; `etat` dit où on en est (jamais une liste vide trompeuse). */
export function useCharge<T>(charger: () => Promise<{ data?: T; error?: unknown }>) {
    const [donnees, setDonnees] = useState<T | null>(null);
    const [etat, setEtat] = useState<"chargement" | "ok" | "erreur">("chargement");
    const recharger = useCallback(() => {
        charger().then((res) => {
            if (res.error || res.data === undefined) setEtat("erreur");
            else {
                setDonnees(res.data);
                setEtat("ok");
            }
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    useEffect(() => {
        recharger();
    }, [recharger]);
    return { donnees, etat, recharger, remplacer: setDonnees };
}

/** L'adresse du portail, réglée dans l'environnement du déploiement ; vide : « Ouvrir son portail » est désactivé. */
export const ADRESSE_PORTAIL = (process.env.NEXT_PUBLIC_PORTAIL_URL ?? "").replace(/\/$/, "");
// Partie 3, 17b : la route d'entrée du portail est /api/auth/entree-mark, et le lien porte le client avant le jeton (« client.jeton »).
export const lienDEntree = (lien: string) => `${ADRESSE_PORTAIL}/api/auth/entree-mark?lien=${encodeURIComponent(lien)}`;

/** Les appels de l'API partent après la connexion (l'intercepteur d'authentification n'existe pas avant). */
export function Pret({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();
    if (loading || !user) return <EtatVide cas="chargement" />;
    return <>{children}</>;
}

/** Une couleur pleine par client (jetons du thème), pour son avatar : initiales en blanc, jamais de fond pastel (E92). */
const COULEURS_CLIENT = ["var(--acc)", "var(--violet-relation)", "var(--etat-fait)", "var(--marque-relation)"];
const initiales = (nom: string) =>
    nom
        .split(/\s+/)
        .filter(Boolean)
        .map((m) => m[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();

/**
 * La pastille d'un client : son logo quand il en a un (point 15, `logo`), sinon ses initiales colorées. Le logo ne sert que là où
 * `id` est l'organisation du client lui-même (pas pour l'auteur d'un message) ; une image qui ne charge pas retombe sur l'initiale.
 */
export function AvatarClient({ id, nom, taille = 36, logo = false }: { id: number; nom: string; taille?: number; logo?: boolean }) {
    const adresse = useLogoEspace(logo ? id : null);
    const [casse, setCasse] = useState<string | null>(null);
    if (adresse && casse !== adresse)
        return (
            // eslint-disable-next-line @next/next/no-img-element -- adresse locale (blob) du logo lu avec la session
            <img
                src={adresse}
                alt=""
                aria-hidden
                data-logo-client
                width={taille}
                height={taille}
                onError={() => setCasse(adresse)}
                className="shrink-0 rounded-md border bg-card object-contain"
                style={{ width: taille, height: taille }}
            />
        );
    return (
        <span
            aria-hidden
            className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
            style={{ width: taille, height: taille, backgroundColor: COULEURS_CLIENT[id % COULEURS_CLIENT.length], fontSize: taille * 0.36 }}
        >
            {initiales(nom)}
        </span>
    );
}

/** « En service » (un agent publié) ou « En installation » : lu du serveur, jamais deviné. */
export function EtatClient({ etat }: { etat: string }) {
    const { t } = useLangue();
    return (
        <PointEtat etat={etat === "actif" ? "publie" : "brouillon"}>
            {etat === "actif" ? t({ en: "In service", fr: "En service" }) : t({ en: "Being set up", fr: "En installation" })}
        </PointEtat>
    );
}
