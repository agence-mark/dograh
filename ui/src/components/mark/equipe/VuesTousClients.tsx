"use client";

/**
 * [.mark] Builder partie 3, sous-lot 10 (SE-3, E-3) : les vues « tous clients » de l'équipe, dans le Labo.
 *
 * Lecture seule : les deux listes (appels, conversations du builder) viennent de `GET /vues-equipe/...`, qui ne montre que les clients
 * que le rôle du compte ouvre. Une ligne mène chez le client (là où l'on agit). Requêtes partagées avec le reste de la page : une par liste.
 */
import { MessageSquare, Phone } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { chatDeTousLesClientsApiV1VuesEquipeChatGet, conversationsDeTousLesClientsApiV1VuesEquipeConversationsGet } from "@/client";
import type { ConversationsEquipeResponse, FilsEquipe } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { espaceDe } from "@/components/mark/studio/navigation-studio";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const PAR_PAGE = 25;

/** Vrai dans le Labo : c'est là, et seulement là, que la vue « tous clients » existe. */
export const useDansLeLabo = () => espaceDe(usePathname() ?? "/labo").espace === "labo";

type Charge<T> = { etat: "chargement" } | { etat: "erreur" } | { etat: "acces" } | { etat: "pret"; donnees: T };

const T = {
    client: { en: "Client", fr: "Client" },
    agent: { en: "Agent", fr: "Agent" },
    conversation: { en: "Conversation", fr: "Conversation" },
    mode: { en: "Mode", fr: "Mode" },
    etat: { en: "State", fr: "État" },
    quand: { en: "When", fr: "Quand" },
    titre: { en: "Title", fr: "Titre" },
    changements: { en: "Changes", fr: "Changements" },
    aucunAppel: { en: "No call yet", fr: "Aucun appel encore" },
    aucunChat: { en: "No chat yet", fr: "Aucun chat encore" },
    termine: { en: "Done", fr: "Terminée" },
    enCours: { en: "Ongoing", fr: "En cours" },
    precedent: { en: "Previous", fr: "Précédent" },
    suivant: { en: "Next", fr: "Suivant" },
};

/** Charge une page d'une liste « tous clients ». Une lecture refusée (403) dit « accès », une panne « erreur ». */
function usePage<T>(lire: (decalage: number) => Promise<{ data?: T; error?: unknown; response?: { status?: number } }>) {
    const { user, loading } = useAuth();
    const [decalage, setDecalage] = useState(0);
    const [charge, setCharge] = useState<Charge<T>>({ etat: "chargement" });
    const charger = useCallback(async () => {
        setCharge({ etat: "chargement" });
        const r = await lire(decalage);
        if (r.error || r.data === undefined) setCharge({ etat: r.response?.status === 403 ? "acces" : "erreur" });
        else setCharge({ etat: "pret", donnees: r.data });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [decalage]);
    useEffect(() => {
        if (loading || !user) return;
        void charger();
    }, [loading, user, charger]);
    return { charge, decalage, setDecalage, recharger: charger };
}

function Pagination({ decalage, total, aller }: { decalage: number; total: number; aller: (d: number) => void }) {
    const { t } = useLangue();
    if (total <= PAR_PAGE) return null;
    return (
        <div className="flex items-center justify-end gap-2 pt-3 text-xs text-muted-foreground">
            <span>
                {decalage + 1}-{Math.min(decalage + PAR_PAGE, total)} / {total}
            </span>
            <Button size="sm" variant="ghost" disabled={decalage === 0} onClick={() => aller(Math.max(0, decalage - PAR_PAGE))}>
                {t(T.precedent)}
            </Button>
            <Button size="sm" variant="ghost" disabled={decalage + PAR_PAGE >= total} onClick={() => aller(decalage + PAR_PAGE)}>
                {t(T.suivant)}
            </Button>
        </div>
    );
}

/** Les appels de tous les clients ouverts : la colonne « Client » de la maquette. */
export function ConversationsTousClients() {
    const { t } = useLangue();
    const { charge, decalage, setDecalage, recharger } = usePage<ConversationsEquipeResponse>((d) =>
        conversationsDeTousLesClientsApiV1VuesEquipeConversationsGet({ query: { limit: PAR_PAGE, offset: d } }),
    );
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={() => void recharger()} />;
    const { conversations, total } = charge.donnees;
    if (conversations.length === 0) return <EtatVide cas="premier" icone={Phone} titre={t(T.aucunAppel)} />;
    return (
        <>
            <Tableau colonnes={[{ titre: t(T.client) }, { titre: t(T.agent) }, { titre: t(T.conversation) }, { titre: t(T.mode) }, { titre: t(T.etat) }, { titre: t(T.quand), droite: true }]}>
                {conversations.map((c) => (
                    <Ligne key={c.id} href={`/clients/${c.organization_id}/conversations`}>
                        <Cellule principale>{c.organization_nom}</Cellule>
                        <Cellule>{c.workflow_name ?? ""}</Cellule>
                        <Cellule>{c.name}</Cellule>
                        <Cellule>{c.mode}</Cellule>
                        <Cellule>{c.is_completed ? t(T.termine) : t(T.enCours)}</Cellule>
                        <Cellule droite>
                            <DateRelative valeur={c.created_at} />
                        </Cellule>
                    </Ligne>
                ))}
            </Tableau>
            <Pagination decalage={decalage} total={total} aller={setDecalage} />
        </>
    );
}

/** Le Chat du Labo : les conversations du builder de tous les clients ouverts (lecture seule ; on les ouvre chez le client). */
export function ChatTousClients() {
    const { t } = useLangue();
    const { charge, decalage, setDecalage, recharger } = usePage<FilsEquipe>((d) =>
        chatDeTousLesClientsApiV1VuesEquipeChatGet({ query: { limit: PAR_PAGE, offset: d } }),
    );
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={() => void recharger()} />;
    const { fils, total } = charge.donnees;
    if (fils.length === 0) return <EtatVide cas="premier" icone={MessageSquare} titre={t(T.aucunChat)} />;
    return (
        <>
            <Tableau colonnes={[{ titre: t(T.client) }, { titre: t(T.titre) }, { titre: t(T.changements), droite: true }, { titre: t(T.quand), droite: true }]}>
                {fils.map((f) => (
                    <Ligne key={f.id} href={`/clients/${f.organization_id}/chat/${f.id}`}>
                        <Cellule principale>{f.organization_nom}</Cellule>
                        <Cellule>{f.titre}</Cellule>
                        <Cellule droite>{f.changements > 0 ? f.changements : ""}</Cellule>
                        <Cellule droite>
                            <DateRelative valeur={f.modifie_le as string} />
                        </Cellule>
                    </Ligne>
                ))}
            </Tableau>
            <Pagination decalage={decalage} total={total} aller={setDecalage} />
        </>
    );
}
