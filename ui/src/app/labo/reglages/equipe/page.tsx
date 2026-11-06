// [.mark] K1 : Réglages › Équipe et rôles est un onglet de Réglages.
import { redirect } from "next/navigation";

export default function Page() {
    redirect("/labo/reglages?onglet=equipe");
}
