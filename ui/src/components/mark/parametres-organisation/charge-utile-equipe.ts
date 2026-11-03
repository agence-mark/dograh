/**
 * [.mark] Le contenu de l'équipe écrit au serveur (lieux d'une personne, bornes, nettoyage), commun à la fenêtre
 * Équipe et routage de l'écran Entreprise et à ses tests (K4b/J : repris de l'ancien thème, retiré).
 */
import type { Equipe, Personne } from "@/client/types.gen";

/** C1: the same bound as the server (``Personne.description``, 300). */
export const DESCRIPTION_MAX = 300;

/**
 * The places of a person, as a list (lot 11, M5): zero, one or several, a LABEL and never a filter. Read from
 * `etablissements`, else from the legacy single place of an older answer.
 */
export const lieuxDe = (p: Pick<Personne, "etablissement" | "etablissements">): string[] =>
    p.etablissements ?? (p.etablissement ? [p.etablissement] : []);

export const charge_utile_equipe = (equipe: Equipe): Equipe => ({
    personnes: (equipe.personnes ?? []).map((p) => ({
        ...p,
        prenom: p.prenom.trim(),
        nom: p.nom?.trim() || null,
        role: p.role?.trim() || null,
        mail: p.mail?.trim() || null,
        telephone: p.telephone?.trim() || null,
        // Lot 11 (M5): the list is what the screen sends; BOTH fields are emptied to put a person back on
        // « the whole company », and the legacy single place mirrors the first of the list.
        etablissements: lieuxDe(p),
        etablissement: lieuxDe(p)[0] || null,
        // l-agent-collegue, L1 (C1): what the agent knows of the person.
        description: p.description?.trim() || null,
        divulguer_telephone: p.divulguer_telephone ?? false,
        divulguer_mail: p.divulguer_mail ?? false,
        joignable_par_transfert: p.joignable_par_transfert ?? false,
        // l-agent-collegue, L4 (H7): her agenda in each calendar software; null = left as it is.
        agendas:
            p.agendas == null
                ? null
                : Object.fromEntries(Object.entries(p.agendas).map(([s, a]) => [s, (a ?? "").trim()]).filter(([, a]) => a)),
    })),
    sujets: (equipe.sujets ?? []).map((s) => ({
        ...s,
        libelle: s.libelle.trim(),
        mots_declencheurs: (s.mots_declencheurs ?? []).map((m) => m.trim()).filter(Boolean),
    })),
});
