"use client";

/**
 * [.mark] Module Restauration, lot 13 : les appels des écrans Salle, Remises, Envois et Caisse (débrancher, resynchroniser) aux routes du fork
 * ``api/routes/restauration_salle.py`` et ``restauration_caisse.py``. Types calqués sur ``api/schemas/restauration_salle.py``.
 *
 * Le client généré se régénère à la fusion par la fenêtre principale : ce module s'appuie sur le même client HTTP, comme ``donnees.ts``.
 */
import { client } from "@/client/client.gen";

const JSON_ENTETE = { "Content-Type": "application/json" };
const E = (etab: number) => `/api/v1/restauration/etablissements/${etab}`;
export type Reponse<T> = { data?: T; error?: unknown; response?: Response };
const lire = <T>(p: Promise<unknown>) => p as Promise<Reponse<T>>;

// --------------------------------------------------------------------------- la salle

export type Forme = "ronde" | "carree" | "rectangle";
export interface TableDuPlan {
    /** Un identifiant réel (chiffres), ou ``nouveau-…`` pour une table que l'écran vient de poser. */
    id: string;
    nom: string;
    forme: Forme;
    x: number;
    y: number;
    l: number;
    h: number;
    couverts_min: number;
    couverts_max: number;
    assemblable_avec: string[];
    actif?: boolean;
}
export interface ElementDuPlan {
    id: string;
    type: "bar" | "porte";
    x: number;
    y: number;
    l: number;
    h: number;
}
export interface SalleDuPlan {
    id: string;
    nom: string;
    elements: ElementDuPlan[];
    tables: TableDuPlan[];
}
export interface ServiceDeSalle {
    id?: number;
    nom: string;
    jours: number[];
    debut: string;
    fin: string;
    pas_minutes: number;
}
export interface DureeDeGroupe {
    id?: number;
    couverts_min: number;
    couverts_max: number;
    duree_minutes: number;
}
export interface ReglesDeSalle {
    delai_minimal: number;
    jours_a_l_avance: number;
    couverts_max_groupe: number | null;
    couverts_max_creneau: number | null;
}
export type StatutReservation = "confirmee" | "honoree" | "absente";
export interface ReservationLue {
    numero: string;
    jour: string;
    debut_min: number;
    duree_minutes: number;
    couverts: number;
    prenom: string | null;
    telephone: string | null;
    note: string | null;
    table_ids: number[];
    tables: string[];
    statut: StatutReservation;
    cree_par: "agent" | "portail" | "caisse";
}
export interface SalleRendue {
    fuseau: string;
    aujourd_hui: string;
    maintenant_min: number;
    salles: (Omit<SalleDuPlan, "id" | "tables"> & { id: number; tables: (Omit<TableDuPlan, "id" | "assemblable_avec"> & { id: number; assemblable_avec: number[] })[] })[];
    services: ServiceDeSalle[];
    durees: DureeDeGroupe[];
    regles: ReglesDeSalle;
    reservations: ReservationLue[];
}
export const lireLaSalle = (etab: number) => lire<SalleRendue>(client.get({ url: `${E(etab)}/salle`, query: { jours: 30 } }));
export const ecrireLePlan = (etab: number, salles: SalleDuPlan[]) =>
    lire<SalleRendue>(client.put({ url: `${E(etab)}/salle/plan`, body: { salles }, headers: JSON_ENTETE }));
export const ecrireLesCreneaux = (etab: number, corps: { services?: ServiceDeSalle[]; durees?: DureeDeGroupe[]; regles?: Partial<ReglesDeSalle> }) =>
    lire<SalleRendue>(client.put({ url: `${E(etab)}/salle/creneaux`, body: corps, headers: JSON_ENTETE }));
export const poserLeStatut = (etab: number, numero: string, statut: StatutReservation) =>
    lire<{ ok: boolean }>(client.post({ url: `${E(etab)}/reservations/${numero}/statut`, body: { statut }, headers: JSON_ENTETE }));
/** Une réservation annulée par le restaurant (route du lot 8 : la table se libère tout de suite). */
export const annulerLaReservation = (etab: number, numero: string) =>
    lire<unknown>(client.post({ url: `${E(etab)}/reservations/${numero}/annuler`, headers: JSON_ENTETE }));

// --------------------------------------------------------------------------- les remises

export const MECANISMES = [
    "pourcentage", "montant", "x_achetes_y_offert", "deuxieme_moitie_prix", "prix_du_jour", "seuil_panier",
    "passage_en_menu", "taille_superieure", "offre_famille", "creneau", "nouveaute", "fidelite",
] as const;
export type Mecanisme = (typeof MECANISMES)[number];
export type EtatRemise = "brouillon" | "active" | "suspendue" | "terminee";
export interface RemiseLue {
    id: number;
    nom: string;
    mecanisme: Mecanisme | string;
    declencheur: Record<string, unknown>;
    effet: Record<string, unknown>;
    perimetre: Record<string, unknown>;
    cumul: "exclusive" | "cumulable";
    limite: Record<string, unknown> | null;
    phrase: string | null;
    moment: Record<string, unknown> | null;
    debut: string | null;
    fin: string | null;
    etat: EtatRemise;
    ref_caisse: string | null;
    source: "caisse" | "portail" | "mark" | "agent" | "import";
    maj_le: string;
    utilisations: number;
    ca_centimes: number;
    remise_centimes: number;
    /** M38 : les offres de cette remise dites par l'agent, et celles qui se sont retrouvées sur une commande. */
    dite: number;
    acceptee: number;
}
export interface RemisesRendues {
    remises: RemiseLue[];
    lecture_seule: boolean;
    prise: string;
}
export interface RemiseEcrite {
    nom: string;
    mecanisme: Mecanisme;
    declencheur: Record<string, unknown>;
    effet: Record<string, unknown>;
    perimetre: Record<string, unknown>;
    cumul: "exclusive" | "cumulable";
    limite: Record<string, unknown> | null;
    phrase: string | null;
    moment: Record<string, unknown> | null;
    debut: string | null;
    fin: string | null;
    etat: "brouillon" | "active";
}
export const lireLesRemises = (etab: number) => lire<RemisesRendues>(client.get({ url: `${E(etab)}/remises` }));
export const creerUneRemise = (etab: number, corps: RemiseEcrite) => lire<RemisesRendues>(client.post({ url: `${E(etab)}/remises`, body: corps, headers: JSON_ENTETE }));
export const modifierUneRemise = (etab: number, id: number, corps: RemiseEcrite) =>
    lire<RemisesRendues>(client.put({ url: `${E(etab)}/remises/${id}`, body: corps, headers: JSON_ENTETE }));
export const changerLEtatDUneRemise = (etab: number, id: number, etat: EtatRemise) =>
    lire<RemisesRendues>(client.post({ url: `${E(etab)}/remises/${id}/etat`, body: { etat }, headers: JSON_ENTETE }));
export const supprimerUneRemise = (etab: number, id: number) => lire<RemisesRendues>(client.delete({ url: `${E(etab)}/remises/${id}` }));

// --------------------------------------------------------------------------- les envois (M7)

export type DeclencheurDEnvoi = "commande_enregistree" | "reservation_enregistree" | "reservation_modifiee" | "reservation_annulee" | "carte" | "avis" | "heure_changee";
export interface EnvoiLu {
    declencheur: DeclencheurDEnvoi;
    type: "sms";
    texte: string;
    actif: boolean;
    texte_par_defaut: string;
    trous: string[];
}
export const lireLesEnvois = (etab: number) => lire<{ envois: EnvoiLu[] }>(client.get({ url: `${E(etab)}/envois` }));
export const ecrireLesEnvois = (etab: number, envois: { declencheur: DeclencheurDEnvoi; texte?: string; actif?: boolean }[]) =>
    lire<{ envois: EnvoiLu[] }>(client.put({ url: `${E(etab)}/envois`, body: { envois }, headers: JSON_ENTETE }));

// --------------------------------------------------------------------------- la caisse (M6)

export interface BilanDeResynchro {
    ok: boolean;
    erreur: string | null;
    carte: boolean;
    ruptures: boolean;
    etat: boolean;
}
export const debrancherLaCaisse = (etab: number) => lire<{ ok: boolean }>(client.delete({ url: `${E(etab)}/caisse` }));
export const resynchroniserLaCaisse = (etab: number) => lire<BilanDeResynchro>(client.post({ url: `${E(etab)}/caisse/resynchroniser`, headers: JSON_ENTETE }));
export const brancherLaCaisse = (etab: number) =>
    lire<{ adresse_autorisation: string }>(client.post({ url: `${E(etab)}/caisse/brancher`, body: { prise: "hubrise" }, headers: JSON_ENTETE }));

export interface CommandeRecente {
    numero: string;
    numero_court: string;
    mode: string;
    statut: string;
    total: number;
    ref_caisse: string | null;
    le: string;
    moyen: string | null;
}
export const lireLesCommandesRecentes = (etab: number) => lire<{ commandes: CommandeRecente[] }>(client.get({ url: `${E(etab)}/commandes-recentes`, query: { limite: 10 } }));
export const poserLImprimante = (etab: number) =>
    lire<{ adresse: string }>(client.post({ url: `${E(etab)}/imprimante`, body: { mode_planifiee: "differe", minutes_avant: 20 }, headers: JSON_ENTETE }));

export interface EssaiRendu {
    statut: "enregistree" | "refusee";
    raison: string | null;
    numero_court: string | null;
    envoi: string | null;
}
export const envoyerUneCommandeDEssai = (etab: number) => lire<EssaiRendu>(client.post({ url: `${E(etab)}/caisse/commande-d-essai`, headers: JSON_ENTETE }));
