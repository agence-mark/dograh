/**
 * [.mark] Partie 3, lot 14 (J-1, SE-19) : les logos officiels des logiciels du catalogue.
 *
 * Les fichiers viennent d'Evan (jamais un logo redessiné). Tant qu'un fichier n'est pas versé, la ligne ou la carte
 * montre les initiales du logiciel. Pour en ajouter un : déposer le fichier dans `ui/public/logos/` et ajouter UNE ligne
 * ici, clé = la clé du logiciel (`integration` du catalogue), valeur = son adresse publique.
 * Exemple : `google_agenda: "/logos/google-agenda.svg"`.
 */
export const LOGOS: Record<string, string> = {};

export const logoDe = (integration: string | null | undefined): string | null => (integration ? (LOGOS[integration] ?? null) : null);
