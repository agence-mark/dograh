import { getSignupEnabled } from "@/lib/auth/config";

import { FormulaireConnexion } from "./FormulaireConnexion";

// L'état de l'installation (vide ou non) est lu côté serveur avant l'affichage : pas de lien qui apparaît après coup.
export const dynamic = "force-dynamic";

export default async function PageConnexion() {
    // `signup_enabled` est vrai seulement tant que l'installation n'a aucun compte (U2 ter).
    return <FormulaireConnexion premierCompte={await getSignupEnabled()} />;
}
