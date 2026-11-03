"use client";

import { ScrollText } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { lireLeJournalApiV1EquipeMarkJournalGet } from "@/client/sdk.gen";
import type { JournalLigne } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { fenetrePage, Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { detailFromError } from "@/lib/apiError";
import { listerEspaces } from "@/lib/espaces";

/** Les gestes écrits au journal, dits en clair ; une clé inconnue s'affiche telle quelle (jamais masquée). */
const GESTES: Record<string, Texte> = {
    "invitation.creer": { en: "Invited a member", fr: "A invité un membre" },
    "invitation.accepter": { en: "Joined the team", fr: "A rejoint l'équipe" },
    "invitation.annuler": { en: "Cancelled an invitation", fr: "A annulé une invitation" },
    "membre.role": { en: "Changed a member's role", fr: "A changé le rôle d'un membre" },
    "membre.retirer": { en: "Removed a member", fr: "A retiré un membre" },
    "role.creer": { en: "Created a role", fr: "A créé un rôle" },
    "role.modifier": { en: "Changed a role", fr: "A modifié un rôle" },
    "role.supprimer": { en: "Deleted a role", fr: "A supprimé un rôle" },
    "profil.mot_de_passe": { en: "Changed their password", fr: "A changé son mot de passe" },
    "espace.labo": { en: "Marked the Lab", fr: "A marqué le Labo" },
    "espace.nom": { en: "Renamed a space", fr: "A renommé un espace" },
    "agents.modifier": { en: "Changed an agent or a setting", fr: "A modifié un agent ou un réglage" },
    "agents.publier": { en: "Published", fr: "A publié" },
    "agents.supprimer": { en: "Archived an agent", fr: "A archivé un agent" },
    "builder.lancer": { en: "Used the builder", fr: "A utilisé le builder" },
    "tests.jouer": { en: "Played a test", fr: "A joué un test" },
    "clients.creer": { en: "Created a client", fr: "A créé un client" },
    "clients.exporter_ramener": { en: "Exported or brought back an agent", fr: "A exporté ou ramené un agent" },
    "cles.gerer": { en: "Changed keys", fr: "A modifié des clés" },
    "telephonie.gerer": { en: "Changed telephony", fr: "A modifié la téléphonie" },
    "atelier.regler": { en: "Changed the workshop settings", fr: "A réglé l'atelier" },
};

const qui = (l: JournalLigne) => [l.prenom, l.nom].filter(Boolean).join(" ") || l.auteur;

/** [.mark] Le journal (U2 ter) : qui, quoi, quel espace, quand. Paginé côté serveur, 25 par page. */
export function VueJournal() {
    const { t } = useLangue();
    const [page, setPage] = useState(0);
    const [donnees, setDonnees] = useState<{ lignes: JournalLigne[]; total: number } | null>(null);
    const [espaces, setEspaces] = useState<Record<number, string>>({});

    useEffect(() => {
        listerEspaces()
            .then((liste) => setEspaces(Object.fromEntries(liste.map((e) => [e.id, e.nom]))))
            .catch(() => setEspaces({}));
    }, []);

    useEffect(() => {
        lireLeJournalApiV1EquipeMarkJournalGet({ query: fenetrePage(page) }).then((res) => {
            if (res.error || !res.data) {
                toast.error(detailFromError(res.error, t({ en: "The journal could not be read", fr: "Le journal n'a pas pu être lu" })));
                return;
            }
            setDonnees({ lignes: res.data.lignes, total: res.data.total });
        });
    }, [page, t]);

    if (!donnees) return <EtatVide cas="chargement" />;

    return (
        <div>
            <TitreTableau titre={t({ en: "Journal", fr: "Journal" })} />
            {donnees.total === 0 ? (
                <EtatVide cas="premier" icone={ScrollText} titre={t({ en: "Nothing written yet", fr: "Rien d'écrit pour l'instant" })} />
            ) : (
                <Paginee total={donnees.total} page={page} changerPage={setPage}>
                    <Tableau
                        colonnes={[
                            { titre: t({ en: "When", fr: "Quand" }) },
                            { titre: t({ en: "Who", fr: "Qui" }) },
                            { titre: t({ en: "What", fr: "Quoi" }) },
                            { titre: t({ en: "Space", fr: "Espace" }) },
                        ]}
                    >
                        {donnees.lignes.map((l) => (
                            <Ligne key={l.id}>
                                <Cellule principale>{new Date(l.quand).toLocaleString()}</Cellule>
                                <Cellule>{qui(l)}</Cellule>
                                <Cellule>{GESTES[l.action] ? t(GESTES[l.action]) : l.action}</Cellule>
                                <Cellule>{l.organization_id != null ? (espaces[l.organization_id] ?? `#${l.organization_id}`) : "—"}</Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                </Paginee>
            )}
        </div>
    );
}
