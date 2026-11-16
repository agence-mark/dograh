"use client";

/**
 * [.mark] Module Restauration, lot 20 : les appels de l'écran Outils › Simulateurs › Caisse / POS et de la fenêtre Caisse / POS de l'essai aux routes
 * ``api/routes/restauration_caisse_demo.py`` (Labo seulement) et ``restauration_scan.py`` (lire la photo d'une carte).
 *
 * Même convention que ``donnees.ts`` : le client HTTP rend `{ data, error }` sans jamais lever ; le client généré se régénère à la fusion par la fenêtre
 * principale. Montants de la carte en centimes ; les saisies de l'écran (euros, minutes) se convertissent ici, jamais dans le composant.
 */
import { client } from "@/client/client.gen";

import type { Reponse } from "./donnees";

const JSON_ENTETE = { "Content-Type": "application/json" };
const RACINE = "/api/v1/restauration/caisse-demo";
const lire = <T>(p: Promise<unknown>) => p as Promise<Reponse<T>>;

export type EtatResto = "ouvert" | "ferme" | "deborde";
export interface Comportement {
    reponse?: "accepte" | "controle" | "silence" | "panne";
    controles?: string[];
    delai_s?: number;
    acceptation?: "auto" | "manuelle" | "refus";
    doublon?: boolean;
    /** Les imprévus pendant l'appel, déclenchés tout seuls par la caisse de démo : le produit visé (son identifiant, ou « auto » : le premier), un prix qui change, la commande reçue deux fois. */
    rupture_plein_appel?: string | null;
    carte_changee?: boolean;
    commande_deux_fois?: boolean;
}
export interface Zone {
    nom: string;
    communes: string;
    /** Centimes. */
    frais: number;
    minimum: number;
    delai: number;
}
export interface ClientConnu {
    first_name: string | null;
    phone: string | null;
    address_1: string | null;
    delivery_notes: string | null;
}
export interface Reglages {
    delai: number;
    types_de_commande: string[];
    paiements: string[];
    zones: Zone[];
}
export interface RestoResume {
    id: number;
    nom: string;
    point_de_vente: string;
    etat: EtatResto;
    minutes_en_plus: number;
    reglages: Reglages & Record<string, unknown>;
    comportement: Comportement;
    scenario: string | null;
    etablissement_cle: string | null;
    branche: boolean;
}
export interface Declinaison {
    id: string;
    nom: string;
    code_caisse?: string;
    prix: number;
}
export interface ProduitDeTest {
    id: string;
    nom: string;
    description: string | null;
    categorie_id: string | null;
    declinaisons: Declinaison[];
    [autre: string]: unknown;
}
export interface CarteDeTest {
    format: string;
    categories: { id: string; nom: string }[];
    produits: ProduitDeTest[];
    groupes: unknown[];
    formules: unknown[];
}
export interface CommandeRecue {
    ref: string;
    numero: string | null;
    statut: string;
    mode: string | null;
    total: string | null;
    heure_confirmee: string | null;
    creee_le: string;
    lignes: { nom: string; taille: string | null; quantite: string; prix: string; options: string[] }[];
    remises: string[];
    paiements: string[];
}
export interface RestoDetail extends RestoResume {
    carte: CarteDeTest;
    stocks: { sku_ref?: string; option_ref?: string; stock: string }[];
    clients: ClientConnu[];
    commandes: CommandeRecue[];
    messages: { id: string; type: string; statut: string; tentatives: number }[];
}
export interface ScenarioRendu {
    cle: string;
    nom: string;
    etat: EtatResto;
    minutes_en_plus: number;
    comportement: Comportement;
    livre?: boolean;
}
export interface ListeRendue {
    restaurants: RestoResume[];
    scenarios: ScenarioRendu[];
    etablissements: { id: number; cle: string; nom: string }[];
}

export const lireLEtat = () => lire<{ active: boolean }>(client.get({ url: `${RACINE}/etat` }));
export const lireLesRestos = () => lire<ListeRendue>(client.get({ url: `${RACINE}/restaurants` }));
export const lireUnResto = (id: number) => lire<RestoDetail>(client.get({ url: `${RACINE}/restaurants/${id}` }));
export const creerUnResto = (nom: string, modeleDe?: number) =>
    lire<RestoDetail>(client.post({ url: `${RACINE}/restaurants`, body: { nom, ...(modeleDe ? { modele_de: modeleDe } : {}) }, headers: JSON_ENTETE }));
export const reglerUnResto = (id: number, champs: Record<string, unknown>) =>
    lire<RestoDetail>(client.put({ url: `${RACINE}/restaurants/${id}`, body: champs, headers: JSON_ENTETE }));
export const dupliquerUnResto = (id: number) => lire<RestoDetail>(client.post({ url: `${RACINE}/restaurants/${id}/dupliquer` }));
export const supprimerUnResto = (id: number) => lire<{ ok: boolean }>(client.delete({ url: `${RACINE}/restaurants/${id}` }));
export const importerUneCarte = (id: number, carte: unknown) =>
    lire<{ produits: number; categories: number }>(client.post({ url: `${RACINE}/restaurants/${id}/carte/import`, body: { carte }, headers: JSON_ENTETE }));
export const lireUnePhoto = (id: number, image: string, typeImage: string) =>
    lire<{ carte: CarteDeTest; lus: number; ecartes: number }>(
        client.post({ url: `${RACINE}/restaurants/${id}/carte/photo`, body: { image, type_image: typeImage }, headers: JSON_ENTETE }),
    );
export const faireUnGeste = (id: number, geste: Record<string, unknown>) =>
    lire<{ ok: boolean }>(client.post({ url: `${RACINE}/restaurants/${id}/gestes`, body: geste, headers: JSON_ENTETE }));
export const brancherUnResto = (id: number, etablissementId: number) =>
    lire<{ ok: boolean; passif: boolean }>(client.post({ url: `${RACINE}/restaurants/${id}/brancher`, body: { etablissement_id: etablissementId }, headers: JSON_ENTETE }));
export const mettreUnScenarioEnPlace = (id: number, scenario: string) =>
    lire<RestoDetail>(client.post({ url: `${RACINE}/restaurants/${id}/scenario`, body: { scenario }, headers: JSON_ENTETE }));
export const enregistrerUnScenario = (id: number, nom: string) =>
    lire<{ cle: string }>(client.post({ url: `${RACINE}/restaurants/${id}/scenarios`, body: { nom }, headers: JSON_ENTETE }));
export const supprimerUnScenario = (cle: string) => lire<{ ok: boolean }>(client.delete({ url: `${RACINE}/scenarios/${encodeURIComponent(cle)}` }));
export const lireLeReglageDuScan = () => lire<{ actif: boolean }>(client.get({ url: "/api/v1/restauration/scan-carte" }));
export const poserLeReglageDuScan = (actif: boolean) =>
    lire<{ actif: boolean }>(client.put({ url: "/api/v1/restauration/scan-carte", body: { actif }, headers: JSON_ENTETE }));
/** Le panier d'un appel en cours (lot 15) : ce que le direct dit de la commande qui se remplit. */
export interface PanierEnCours {
    version: number;
    mode: string | null;
    lignes: { nom: string; quantite: number }[];
}
export const lireLePanier = (etablissementId: number, appelId: number) =>
    lire<PanierEnCours>(client.get({ url: `/api/v1/restauration/etablissements/${etablissementId}/appels/${appelId}/panier` }));

// --------------------------------------------------------------------------- les conversions de l'écran (euros saisis <-> centimes gardés)

/** « 3,5 » ou « 3.50 » en centimes ; un texte qui n'est pas un montant vaut 0 (jamais NaN dans une écriture). */
export const enCentimes = (saisie: string): number => {
    const v = Math.round(Number(String(saisie).replace(",", ".")) * 100);
    return Number.isFinite(v) && v > 0 ? v : 0;
};
/** Des centimes en euros à saisir : « 12,5 » (sans zéros inutiles). */
export const enEuros = (centimes: number): string => (centimes / 100).toString().replace(".", ",");
/** Un nom de produit et de catégorie vers un identifiant de la carte commune (stable, sans accent). */
export const identifiantDe = (texte: string): string =>
    texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) || "X";
