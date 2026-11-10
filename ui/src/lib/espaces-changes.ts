// [.mark] Correctifs d'écran, point 14 : un espace renommé se dit partout sans recharger la page. Chaque endroit qui lit le
// nom d'un espace (sélecteur, miettes, menu, accueil) s'abonne ici ; `reglerEspace` signale. La version permet aux lecteurs
// qui gardent une lecture en mémoire de savoir qu'elle est périmée, sans dépendre de l'ordre des abonnés.
type Ecouteur = () => void;
const ecouteurs = new Set<Ecouteur>();
let version = 0;

/** S'abonner aux changements d'espaces (nom, rôle de Labo). Rend la fonction qui se désabonne. */
export function surChangementDEspaces(ecouteur: Ecouteur): () => void {
    ecouteurs.add(ecouteur);
    return () => {
        ecouteurs.delete(ecouteur);
    };
}

/** Le compteur des changements : une lecture faite à une version plus ancienne est périmée. */
export const versionDesEspaces = () => version;

export function signalerChangementDEspaces(): void {
    version += 1;
    ecouteurs.forEach((e) => e());
}
