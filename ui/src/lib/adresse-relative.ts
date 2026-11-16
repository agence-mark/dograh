/**
 * [.mark] Une redirection du backend (FastAPI : barre finale ajoutée ou retirée) porte l'adresse INTERNE du backend, que ni le navigateur ni ce
 * proxy n'atteignent forcément (502 en production). On ne la suit jamais ici : on la rend au navigateur avec une adresse relative, qui revient
 * par ce proxy. Une adresse qui ne vise pas l'API est laissée telle quelle.
 */
export function adresseRelative(location: string, base: string) {
  try {
    const cible = new URL(location, base);
    return cible.pathname.startsWith("/api/") ? `${cible.pathname}${cible.search}` : location;
  } catch {
    return location;
  }
}
