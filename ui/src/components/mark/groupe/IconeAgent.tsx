/**
 * [.mark] L'icône qui dit la place d'un agent dans son groupe : agent seul, principal d'un groupe, spécialisé. Une seule
 * définition pour la liste des agents et la barre d'un agent (correctifs d'écran, points 3 et 16).
 */
import { Bot, UserRound, Users } from "lucide-react";

export type RoleIcone = "simple" | "principal" | "specialise";

export const IconeAgent = ({ role, className = "size-4" }: { role: RoleIcone; className?: string }) => {
    const Icone = role === "principal" ? Users : role === "specialise" ? UserRound : Bot;
    return <Icone className={`${className} shrink-0 text-muted-foreground`} aria-hidden data-icone-agent={role} />;
};
