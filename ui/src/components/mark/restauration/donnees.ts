"use client";

/**
 * [.mark] Module Restauration, lot 12 : les appels des écrans du fork (Entreprise › Carte, Livraison, Réglages restaurant) aux routes
 * ``api/routes/restauration_ecran.py`` et ``restauration_caisse.py``.
 *
 * Le client généré se régénère à la fusion par la fenêtre principale (un sous-agent ne commite jamais le client généré) : ce module
 * s'appuie sur le même client HTTP et se remplace alors par les fonctions générées. Les types sont ceux des schémas de
 * ``api/schemas/restauration_ecran.py``. Montants en centimes.
 */
import { client } from "@/client/client.gen";

const JSON_ENTETE = { "Content-Type": "application/json" };
const RACINE = "/api/v1/restauration";

/** Le client rend `{ data, error }` sans jamais lever : une réponse typée à la main. */
export type Reponse<T> = { data?: T; error?: unknown; response?: Response };
const lire = <T>(p: Promise<unknown>) => p as Promise<Reponse<T>>;

// --------------------------------------------------------------------------- le module

export interface EtablissementDuModule {
    id: number;
    nom: string;
}
export interface ModuleRendu {
    actif: boolean;
    etablissements: EtablissementDuModule[];
}
export const lireLeModule = () => lire<ModuleRendu>(client.get({ url: `${RACINE}/module` }));
export const poserLeModule = (actif: boolean) =>
    lire<ModuleRendu>(client.put({ url: `${RACINE}/module`, body: { actif }, headers: JSON_ENTETE }));

// --------------------------------------------------------------------------- la carte

export type Portee = "enseigne" | "etablissement" | "exception";
export interface Surcouche {
    synonymes: string[];
    synonymes_a_relire: string[];
    etoile: boolean;
    lexique: string[];
    phrase: string | null;
    /** Le produit contient de l'alcool (surcouche) : un titre-restaurant ne le paie pas. */
    alcool?: boolean;
}
export interface Declinaison {
    id: string;
    nom: string;
    code_caisse: string | null;
    prix: number;
    prix_par_mode: Record<string, number> | null;
    vendable: boolean;
}
export interface Produit extends Surcouche {
    id: string;
    nom: string;
    description: string | null;
    categorie_id: string | null;
    ingredients: { nom: string; retirable?: boolean }[];
    /** `null` = inconnu, `[]` = aucun, sinon les codes parmi les 14. */
    allergenes: string[] | null;
    origine: string | null;
    tva_par_mode: Record<string, number>;
    declinaisons: Declinaison[];
    groupes: string[];
    source: string;
    maj_le?: string | null;
    portee: Portee;
}
export interface OptionDeGroupe {
    id: string;
    nom: string;
    code_caisse: string | null;
    prix: number;
    retirable: boolean;
}
export interface Groupe {
    id: string;
    nom: string;
    min: number;
    max: number;
    max_par_option: number;
    defaut: string[];
    role: "choix" | "supplement" | "moities";
    options: OptionDeGroupe[];
    portee: Portee;
}
export interface Formule {
    id: string;
    nom: string;
    code_caisse: string | null;
    prix: number;
    lignes: unknown;
    portee: Portee;
}
export interface Categorie extends Surcouche {
    id: string;
    nom: string;
    parent_id: string | null;
    ordre: number;
    portee: Portee;
}
export interface Rupture {
    code_caisse: string;
    disponible: boolean;
    stock: number | null;
    debut: string;
    fin: string | null;
    source: string;
}
export interface CarteRendue {
    version: number;
    categories: Categorie[];
    produits: Produit[];
    groupes: Groupe[];
    formules: Formule[];
    ruptures: Rupture[];
    derniere_maj: string | null;
    lecture_seule: boolean;
    prise: string;
}
export interface ImportRendu {
    ajoutes: number;
    changes: number;
    retires: number;
    conserves: number;
    sans_code_caisse: number;
    synonymes_proposes: number;
}

const E = (id: number) => `${RACINE}/etablissements/${id}`;

export const lireLaCarte = (etab: number) => lire<CarteRendue>(client.get({ url: `${E(etab)}/carte` }));
export const poserEtoile = (etab: number, ref: string, etoile: boolean) =>
    lire<{ ok: boolean }>(client.put({ url: `${E(etab)}/carte/etoile`, body: { ref, etoile }, headers: JSON_ENTETE }));
export const poserLesSynonymes = (etab: number, ref: string, synonymes: string[]) =>
    lire<{ ok: boolean }>(client.put({ url: `${E(etab)}/carte/synonymes`, body: { ref, synonymes }, headers: JSON_ENTETE }));
/** Ingrédients et allergènes (surcouche quand la caisse porte le produit). Un champ absent reste intact ; `allergenes: null` = inconnu, `[]` = aucun. */
export interface ProduitEcrit {
    ingredients?: { nom: string; retirable: boolean }[];
    allergenes?: string[] | null;
    alcool?: boolean;
}
export const ecrireLeProduit = (etab: number, ref: string, champs: ProduitEcrit) =>
    lire<{ ok: boolean }>(client.put({ url: `${E(etab)}/carte/produit`, body: { ref, ...champs }, headers: JSON_ENTETE }));
export const validerLesSynonymes = (etab: number, ref: string, synonymes?: string[]) =>
    lire<{ ok: boolean }>(client.post({ url: `${E(etab)}/carte/synonymes/relus`, body: { ref, synonymes }, headers: JSON_ENTETE }));
export const importerLaCarte = (etab: number, source: "caisse" | "fichier", carte?: Record<string, unknown>) =>
    lire<ImportRendu>(client.post({ url: `${E(etab)}/carte/import`, body: { source, carte }, headers: JSON_ENTETE }));
/** Une rupture passe par la route de la caisse (elle la pousse à la prise si elle sait la poser). */
export const poserUneRupture = (etab: number, code_caisse: string, disponible: boolean, fin?: string | null) =>
    lire<{ ok: boolean; poussee_a_la_caisse: boolean }>(
        client.post({ url: `${E(etab)}/ruptures`, body: { code_caisse, disponible, fin: fin ?? null }, headers: JSON_ENTETE }),
    );

// --------------------------------------------------------------------------- la livraison

export interface Zone {
    id: number | null;
    nom: string;
    forme: "communes" | "rayon";
    cercle_km: number | null;
    communes: string[];
    exclues: string[];
    frais: number;
    minimum: number;
    gratuite_des: number | null;
    delai: number;
}
export interface CommuneTrouvee {
    insee: string;
    nom: string;
    code_postal: string | null;
    km: number;
    zone_id: number | null;
    refusee: boolean;
}
export interface LivraisonRendue {
    centre_connu: boolean;
    commune: string | null;
    zones: (Zone & { id: number })[];
    communes: CommuneTrouvee[];
}
export const lireLaLivraison = (etab: number, rayon_km: number) =>
    lire<LivraisonRendue>(client.get({ url: `${E(etab)}/livraison`, query: { rayon_km } }));
export const ecrireLesZones = (etab: number, zones: Zone[], rayon_km: number) =>
    lire<LivraisonRendue>(client.put({ url: `${E(etab)}/livraison/zones`, query: { rayon_km }, body: { zones }, headers: JSON_ENTETE }));

// --------------------------------------------------------------------------- les réglages

export type TypeDeCommande = "emporter" | "livraison" | "sur_place" | "reservation";
export type FormatAnnonce = "heure_fixe" | "tranche" | "duree";
export interface TypeReglage {
    type: TypeDeCommande;
    ouvert: boolean;
    pause_jusqu_a: string | null;
    fin_par_jour: Record<string, string>;
    planifiee_permise: boolean;
    delai_minimal: number;
    jours_a_l_avance: number;
    delai_annonce: number | null;
    minutes_ajoutees: number;
    ajout_jusqu_a: string | null;
    annonce: FormatAnnonce;
}
export type MoyenDePaiement = "carte" | "especes" | "titre_restaurant" | "cheque" | "en_ligne";
export interface ReglageDuModule {
    prefixe_numero_court: string;
    numero_mode: "aucun" | "moyen" | "type";
    prefixe_mixte: string;
    notes_libres: boolean;
    titre_alcool_exclu: boolean;
    titre_sans_rendu: boolean;
    pause_caisse_pause_telephone: boolean;
    moyens_paiement: MoyenDePaiement[];
    plafond_titre_restaurant: number | null;
    conservation_client_mois: number;
}
export interface TempsRecurrent {
    id?: number | null;
    type: "emporter" | "livraison" | "sur_place";
    jours: number[];
    debut: string;
    fin: string;
    minutes_ajoutees: number;
}
export type ObjetReglable = "carte" | "ruptures" | "etat" | "horaires";
export interface SourceDeObjet {
    objet: ObjetReglable | "remises" | "clients";
    mode: "caisse" | "ici";
    prise_sait: boolean;
    /** Le restaurant peut choisir de le tenir ici alors que la caisse le porte. */
    reglable: boolean;
}
/** Un jour de fermeture ou plusieurs (début et fin INCLUS, heure locale de l'établissement). */
export interface FermetureExceptionnelle {
    id?: number | null;
    du: string;
    au: string;
    motif?: string | null;
}
export interface ReglagesRendus {
    types: TypeReglage[];
    reglage: ReglageDuModule;
    recurrents: TempsRecurrent[];
    fermetures: FermetureExceptionnelle[];
    envoi_heure_changee: { texte: string | null; actif: boolean };
    seuils: { alerte_sans_reponse_min: number; releve_messages_min: number } | null;
    imprimante: { mode_planifiee: "differe" | "immediat"; minutes_avant: number } | null;
    horaires_fiche: Record<string, { from: string; to: string }[]>;
    horaires_caisse: Record<string, unknown> | null;
    sources: SourceDeObjet[];
    prise: string;
    caisse_porte_l_etat: boolean;
}
export type ReglagesChanges = Partial<{
    types: Partial<TypeReglage> & { type: TypeDeCommande }[];
    reglage: Partial<ReglageDuModule> & { sources?: Partial<Record<ObjetReglable, "caisse" | "ici">> };
    recurrents: TempsRecurrent[];
    fermetures: FermetureExceptionnelle[];
    envoi_heure_changee: { texte?: string; actif?: boolean };
    seuils: Partial<{ alerte_sans_reponse_min: number; releve_messages_min: number }>;
    imprimante: Partial<{ mode_planifiee: "differe" | "immediat"; minutes_avant: number }>;
}>;
export const lireLesReglages = (etab: number) => lire<ReglagesRendus>(client.get({ url: `${E(etab)}/reglages` }));
export const ecrireLesReglages = (etab: number, changes: ReglagesChanges) =>
    lire<ReglagesRendus>(client.put({ url: `${E(etab)}/reglages`, body: changes, headers: JSON_ENTETE }));

export interface LigneDHistorique {
    id: number;
    objet: string;
    objet_dit: string;
    ligne_id: string;
    operation: "insert" | "update" | "delete";
    avant: string | null;
    apres: string | null;
    source: string;
    auteur: string;
    le: string;
}
export const lireLHistorique = (etab: number, avant?: number | null) =>
    lire<{ lignes: LigneDHistorique[]; suite: number | null }>(client.get({ url: `${E(etab)}/historique`, query: { limite: 30, ...(avant ? { avant } : {}) } }));

// --------------------------------------------------------------------------- la caisse (route du lot 9)

export interface CaisseRendue {
    prise: string;
    etat: "aucune" | "ok" | "erreur" | "rompue";
    derniere_erreur: string | null;
    derniere_synchro: string | null;
    point_de_vente: string | null;
    mode_passif: boolean;
    derniere_releve: string | null;
    avertissements: string[];
    etat_caisse: { mode: "normal" | "deborde" | "pause"; minutes_en_plus: number; reprise: string | null; temps_preparation: number | null } | null;
    capacites: Record<string, unknown>;
}
export const lireLaCaisse = (etab: number) => lire<CaisseRendue>(client.get({ url: `${E(etab)}/caisse` }));

// --------------------------------------------------------------------------- le temps (route du lot 6)

export interface TempsRendu {
    types: {
        type: TypeDeCommande;
        ouvert: boolean;
        raison: string | null;
        pause_jusqu_a: string | null;
        minutes_ajoutees: number;
        ajout_jusqu_a: string | null;
        ajout_actif: number;
        format: FormatAnnonce;
        delai_minutes: number | null;
        annonce: { phrase: string; minutes: number | null } | null;
        par_zone: { zone_id: number; nom: string; delai_zone: number; annonce: { phrase: string; minutes: number | null } }[];
    }[];
    lecture_seule: boolean;
    source_de_l_etat: "caisse" | "portail";
}
export const lireLeTemps = (etab: number) => lire<TempsRendu>(client.get({ url: `${E(etab)}/temps` }));
export const poserLeTemps = (
    etab: number,
    corps: { type: TypeDeCommande; minutes_ajoutees: number; jusqu_a?: string | null; pause?: { minutes?: number } | null },
) => lire<TempsRendu>(client.put({ url: `${E(etab)}/temps`, body: corps, headers: JSON_ENTETE }));
