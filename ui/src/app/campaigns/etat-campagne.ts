/**
 * [.mark] K8 : l'état d'une campagne vu par l'écran : le mot, dans les deux langues, et le point d'état du design system
 * (plein = en cours, anneau = pas lancée ou en pause, gris = terminée, rouge = en échec). Une seule table pour la liste
 * et la page d'une campagne.
 */
type EtatPoint = 'publie' | 'brouillon' | 'panne' | 'fini' | 'attente';

export const ETATS_CAMPAGNE: Record<string, { libelle: { en: string; fr: string }; point: EtatPoint }> = {
    created: { libelle: { en: 'Created', fr: 'Créée' }, point: 'brouillon' },
    running: { libelle: { en: 'Running', fr: 'En cours' }, point: 'publie' },
    paused: { libelle: { en: 'Paused', fr: 'En pause' }, point: 'brouillon' },
    completed: { libelle: { en: 'Completed', fr: 'Terminée' }, point: 'fini' },
    failed: { libelle: { en: 'Failed', fr: 'En échec' }, point: 'panne' },
};

export const etatCampagne = (etat: string) =>
    ETATS_CAMPAGNE[etat] ?? { libelle: { en: etat, fr: etat }, point: 'fini' as EtatPoint };
