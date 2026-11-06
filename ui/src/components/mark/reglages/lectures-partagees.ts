"use client";

/**
 * [.mark] C4 : `cerveaux` et `options` du builder, lus UNE fois pour tous les onglets des Réglages du Labo (Builder IA, Appelant
 * simulé, Juge, options de construction). Chaque écriture pose la valeur que le serveur a gardée.
 */
import { lireLesCerveauxApiV1BuilderCerveauxGet, lireLesOptionsApiV1BuilderOptionsGet } from "@/client";
import { creerLecturePartagee } from "@/lib/lecture-partagee";

export const cerveauxPartages = creerLecturePartagee(() => lireLesCerveauxApiV1BuilderCerveauxGet());
export const optionsPartagees = creerLecturePartagee(() => lireLesOptionsApiV1BuilderOptionsGet());
