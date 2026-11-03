// [.mark] U1 : cette adresse monte l'écran actuel dans le nouveau cadre (les écrans refondus le remplaceront).
// [.mark] V1 : `labo` dit au serveur de lire les agents du Labo (la liste se lit côté serveur, sans l'en-tête du navigateur).
import { PageDesAgents } from "@/app/workflow/page-des-agents";

export const dynamic = "force-dynamic";

export default function Page(props: { searchParams?: Promise<{ dossier?: string }>; params?: Promise<{ org?: string }> }) {
    return PageDesAgents({ ...props, labo: true });
}
