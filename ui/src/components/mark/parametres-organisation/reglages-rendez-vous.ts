/**
 * [.mark] The planner's settings as the screen draws them: the lists of controls, shared by the
 * theme « Appointments » (organization and establishment levels) and by the fiche of an
 * establishment (lot 11 of agents-specialises: appointments and zone written WITH the fiche).
 *
 * Moved out of `ThemeRendezVous.tsx` unchanged, so both screens read the same bounds, labels and help.
 */
import type { ReglagesPlanificateur } from "@/client/types.gen";

import { type Texte } from "../langue/langue";

export type Cle = keyof ReglagesPlanificateur;
export type Nombre = { cle: Cle; libelle: Texte; aide: Texte; min: number; max: number; pas?: number };

export const NOMBRES: Nombre[] = [
    { cle: "nombre_creneaux", libelle: { en: "Slots proposed", fr: "Créneaux proposés" }, aide: { en: "How many slots the agent offers at once.", fr: "Combien de créneaux l'agent propose à la fois." }, min: 1, max: 6 },
    { cle: "delai_minimal_h", libelle: { en: "Minimal notice (hours)", fr: "Délai minimal (heures)" }, aide: { en: "No slot sooner than this after the call.", fr: "Aucun créneau avant ce délai après l'appel." }, min: 0, max: 720, pas: 0.5 },
    { cle: "horizon_jours", libelle: { en: "Search horizon (days)", fr: "Horizon de recherche (jours)" }, aide: { en: "How far ahead slots are looked for.", fr: "Jusqu'où les créneaux sont cherchés." }, min: 1, max: 90 },
    { cle: "pas_min", libelle: { en: "Grid of the slots (minutes)", fr: "Pas des créneaux (minutes)" }, aide: { en: "A slot starts every this many minutes from the start of a range.", fr: "Un créneau commence toutes les tant de minutes depuis le début d'une plage." }, min: 5, max: 240 },
];
/** R-7: the fairness window of the « In turn » distribution (shown in the group Distribution). */
export const FENETRE: Nombre = {
    cle: "fenetre_equite_jours",
    libelle: { en: "Fairness window (days)", fr: "Fenêtre du tour de rôle (jours)" },
    aide: {
        en: "« In turn » counts the appointments of the type given over this many days to decide whose turn it is: a shorter window forgets sooner, a longer one evens out over more time.",
        fr: "Le « tour de rôle » compte les rendez-vous du type donnés sur ce nombre de jours pour savoir à qui c'est le tour : une fenêtre courte oublie plus vite, une longue rééquilibre sur plus de temps.",
    },
    min: 1,
    max: 365,
};
export const NOMBRES_TRAJETS: Nombre[] = [
    { cle: "coefficient_trajet", libelle: { en: "Road coefficient", fr: "Coefficient de route" }, aide: { en: "The distance as the crow flies is multiplied by this to estimate the road.", fr: "La distance à vol d'oiseau est multipliée par ce coefficient pour estimer la route." }, min: 1, max: 3, pas: 0.05 },
    { cle: "vitesse_kmh", libelle: { en: "Average speed (km/h)", fr: "Vitesse moyenne (km/h)" }, aide: { en: "Used to turn the road distance into minutes.", fr: "Sert à convertir la distance de route en minutes." }, min: 5, max: 130 },
    { cle: "zone_rayon_km", libelle: { en: "Zone served: radius (km)", fr: "Zone desservie : rayon (km)" }, aide: { en: "Around the establishment. Empty everywhere: no radius.", fr: "Autour de l'établissement. Vide partout : pas de rayon." }, min: 1, max: 1000 },
];
export const CHOIX: Array<{ cle: Cle; libelle: Texte; aide: Texte; options: Array<{ valeur: string; texte: Texte }> }> = [
    {
        cle: "repartition",
        libelle: { en: "Distribution among the team", fr: "Répartition dans l'équipe" },
        aide: { en: "Who gets the appointment. Every attribution is traced (proof of fairness).", fr: "Qui reçoit le rendez-vous. Chaque attribution est tracée (preuve d'équité)." },
        options: [
            { valeur: "premier_libre", texte: { en: "First free", fr: "Premier libre" } },
            { valeur: "tour_de_role", texte: { en: "In turn (the one skipped keeps his priority)", fr: "Tour de rôle (celui qui n'a rien garde sa priorité)" } },
            { valeur: "charge", texte: { en: "Least busy over the horizon", fr: "Le moins chargé sur l'horizon" } },
            { valeur: "zone", texte: { en: "Nearest to the caller", fr: "Le plus proche de l'appelant" } },
        ],
    },
    {
        cle: "repli",
        libelle: { en: "When no slot fits", fr: "Quand aucun créneau ne convient" },
        aide: { en: "A human: when the business is open and someone can take the call. The call-back is said by the agent (sentence phrase_planificateur_rappel) and the request created.", fr: "Un humain : quand l'établissement est ouvert et que quelqu'un peut prendre l'appel. Le rappel est dit par l'agent (phrase phrase_planificateur_rappel) et la demande créée." },
        options: [
            { valeur: "humain_puis_rappel", texte: { en: "A human, then a call-back", fr: "Un humain, puis un rappel" } },
            { valeur: "toujours_rappel", texte: { en: "Always a call-back", fr: "Toujours un rappel" } },
        ],
    },
    {
        cle: "jours_feries",
        libelle: { en: "Public holidays", fr: "Jours fériés" },
        aide: { en: "Computed by the code and closed.", fr: "Calculés par le code et fermés." },
        options: [
            { valeur: "metropole", texte: { en: "Metropolitan France", fr: "France métropolitaine" } },
            { valeur: "alsace_moselle", texte: { en: "Alsace-Moselle (+ Good Friday, 26 December)", fr: "Alsace-Moselle (+ Vendredi saint, 26 décembre)" } },
        ],
    },
];
export const OUI_NON: Array<{ cle: Cle; libelle: Texte; aide: Texte }> = [
    { cle: "trajets_comptes", libelle: { en: "Count the journeys", fr: "Compter les trajets" }, aide: { en: "From the person's establishment to the caller's address and back, as the crow flies. No sure address: not counted (said in the run).", fr: "De l'établissement de la personne à l'adresse de l'appelant et retour, à vol d'oiseau. Sans adresse sûre : non comptés (dit dans le run)." } },
    { cle: "personne_visible", libelle: { en: "The agent may name the person", fr: "L'agent peut nommer la personne" }, aide: { en: "Each slot carries the first name of the person it is with.", fr: "Chaque créneau porte le prénom de la personne." } },
];

/** The name a setting is shown under (D152: said in the window « Apply to all establishments »). */
export const libelleReglage = (cle: string): Texte =>
    [...NOMBRES, FENETRE, ...NOMBRES_TRAJETS, ...CHOIX, ...OUI_NON].find((f) => f.cle === cle)?.libelle ??
    (cle === "plages"
        ? { en: "Booking ranges", fr: "Plages de rendez-vous" }
        : cle === "zone_communes"
          ? { en: "Zone served: communes (INSEE codes)", fr: "Zone desservie : communes (codes INSEE)" }
          : { en: cle, fr: cle });

export const texteValeur = (v: unknown, t: (x: Texte) => string): string =>
    v === null || v === undefined ? "—" : typeof v === "boolean" ? t(v ? { en: "yes", fr: "oui" } : { en: "no", fr: "non" }) : Array.isArray(v) ? v.join(", ") : String(v);
