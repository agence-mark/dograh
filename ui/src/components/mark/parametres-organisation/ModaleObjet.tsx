"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot F7 (D106 à D117), repris par U3 ter (E64) : ce fichier ne garde que
 * les aides de la fenêtre d'une variable (`rendreObjet`, `JaugeObjet`, `CHAMPS_OBJET`). La fenêtre elle-même est
 * `variables/CreateurVariable.tsx`, qui remplace l'ancienne modale des objets.
 */
import type { ObjetEnvoye } from "@/client/types.gen";

import { useLangue } from "../langue/langue";

/** Les champs d'un objet montrés par la modale (l'inventaire d'organisation les compare au client généré). */
export const CHAMPS_OBJET = ["nom", "libelle", "description", "forme", "type", "valeur", "etablissement", "colonnes", "lignes"] as const;

/** Le texte que reçoit l'agent : la même règle que `api/services/objets_agent/rendu.py` et `objet_agent_texte` (SQL). */
export const rendreObjet = (objet: Pick<ObjetEnvoye, "forme" | "valeur" | "colonnes" | "lignes">): string => {
    if (objet.forme === "valeur") return objet.valeur ?? "";
    const rang = (e: { ordre?: number; id?: number | null }) => [e.ordre ?? 0, e.id ?? Number.MAX_SAFE_INTEGER];
    const trier = <E extends { ordre?: number; id?: number | null }>(liste: E[]) =>
        [...liste].sort((a, b) => rang(a)[0] - rang(b)[0] || rang(a)[1] - rang(b)[1]);
    const colonnes = trier(objet.colonnes ?? []);
    if (colonnes.length === 0) return "";
    const entete = colonnes.map((c) => c.libelle).join(" | ");
    const lignes = trier(objet.lignes ?? []).map((l) => colonnes.map((c) => l.valeurs?.[c.libelle] ?? "").join(" | "));
    return [entete, ...lignes].join("\n");
};

/** La taille du texte envoyé à l'agent face au plafond (D112). */
export const JaugeObjet = ({ taille, plafond }: { taille: number; plafond: number }) => {
    const { t } = useLangue();
    const part = Math.min(100, Math.round((taille / Math.max(1, plafond)) * 100));
    return (
        <div className="space-y-1" data-jauge={taille > plafond ? "depasse" : "ok"}>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className={`h-full ${taille > plafond ? "bg-destructive" : "bg-primary"}`} style={{ width: `${part}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">
                {t({ en: `${taille} / ${plafond} characters sent to the agent`, fr: `${taille} / ${plafond} caractères envoyés à l'agent` })}
            </p>
        </div>
    );
};
