"use client";

import { ScrollText } from "lucide-react";
import { useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { listerLesMembresApiV1EquipeMarkMembresGet } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { fenetrePage, Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { listerEspaces } from "@/lib/espaces";

import { type LigneDuJournal as JournalLigne, lireLeJournalFiltre, typesDeGestes } from "./api-cloture";
import { ReglageDureeDuJournal } from "./ReglagesDeLEquipe";

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
    "membre.acces_bloque": { en: "Blocked a member's access", fr: "A bloqué l'accès d'un membre" },
    "membre.acces_actif": { en: "Restored a member's access", fr: "A rétabli l'accès d'un membre" },
    "cle_api.creer": { en: "Created an API key", fr: "A créé une clé d'API" },
    "cle_api.revoquer": { en: "Revoked an API key", fr: "A révoqué une clé d'API" },
    "cle_api.reactiver": { en: "Reactivated an API key", fr: "A réactivé une clé d'API" },
    "cle_api.role": { en: "Changed the role of an API key", fr: "A changé le rôle d'une clé d'API" },
    "cle_api.suspendre": { en: "Suspended an API key", fr: "A suspendu une clé d'API" },
    "cle_api.retablir": { en: "Restored an API key", fr: "A rétabli une clé d'API" },
    "cle_api.interrupteurs_mcp": { en: "Changed the MCP switches of a key", fr: "A changé les interrupteurs MCP d'une clé" },
    "cle_api.regenerer_portail": { en: "Regenerated the portal key", fr: "A régénéré la clé du portail" },
    "reglage.message_acces_bloque": { en: "Changed the blocked-access message", fr: "A changé le message d'accès bloqué" },
    "reglage.duree_journal": { en: "Changed the journal retention", fr: "A changé la durée de garde du journal" },
    "agents.principale_protegee": { en: "Changed the protection of the live version", fr: "A changé la protection de la version en ligne" },
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
    // Partie 3, 17a : les gestes que le portail fait avec la clé du client.
    "connecteurs.autoriser": { en: "Connected or cut a software account", fr: "A branché ou coupé un compte de logiciel" },
    "connecteurs.geste": { en: "Software account gesture", fr: "Geste sur un compte de logiciel" },
    "base_client.connexion_portail": { en: "Opened the portal's access to the client's database", fr: "A ouvert l'accès du portail à la base du client" },
    "contacts.traiter": { en: "Handled a contact (merge, separate, do not memorise)", fr: "A traité un contact (fusion, séparation, ne pas mémoriser)" },
    "tests.automatiser": { en: "Played an agent's tests from an automation", fr: "A joué les tests d'un agent depuis une automatisation" },
    // P-6 : les écritures du Hub (permission « relation.ecrire »).
    "relation.message": { en: "Replied to a client", fr: "A répondu à un client" },
    "relation.fil_modifie": { en: "Changed the follow-up of a thread", fr: "A changé le suivi d'un échange" },
    "relation.note_ajoutee": { en: "Added a note on a client", fr: "A ajouté une note sur un client" },
    "relation.note_supprimee": { en: "Deleted a note on a client", fr: "A supprimé une note sur un client" },
    "relation.temoignage_ajoute": { en: "Added a testimonial", fr: "A ajouté un témoignage" },
    "relation.temoignage_supprime": { en: "Deleted a testimonial", fr: "A supprimé un témoignage" },
};

/** P-1 : le nom du membre ; un compte sans nom se dit « Compte sans nom » (jamais son identifiant brut ni une adresse). */
const quiEst = (l: JournalLigne, sansNom: string) => [l.prenom, l.nom].filter(Boolean).join(" ") || (l.sans_nom ? sansNom : (l.qui ?? l.auteur));

/** [.mark] Le journal (U2 ter) : qui, quoi, quel espace, quand. Paginé côté serveur, 25 par page. */
export function VueJournal() {
    const { t } = useLangue();
    const [page, setPage] = useState(0);
    const [donnees, setDonnees] = useState<{ lignes: JournalLigne[]; total: number } | null>(null);
    const [espaces, setEspaces] = useState<Record<number, string>>({});
    // P-2 : les filtres « Qui » et « Espace », posés côté serveur (le total et les pages suivent le filtre).
    const [membreChoisi, setMembreChoisi] = useState("");
    const [espaceChoisi, setEspaceChoisi] = useState("");
    const [membres, setMembres] = useState<{ id: number; nom: string }[]>([]);
    // Clôture, lot A (D23) : filtres « Type de geste » et « Porte » (écran, API, MCP), posés côté serveur.
    const [types, setTypes] = useState<string[]>([]);
    const [typeChoisi, setTypeChoisi] = useState("");
    const [porteChoisie, setPorteChoisie] = useState("");
    useEffect(() => {
        typesDeGestes().then((res) => setTypes(res.data ?? []));
    }, []);

    useEffect(() => {
        listerEspaces()
            .then((liste) => setEspaces(Object.fromEntries(liste.map((e) => [e.id, e.nom]))))
            .catch(() => setEspaces({}));
    }, []);

    useEffect(() => {
        listerLesMembresApiV1EquipeMarkMembresGet({ query: { limit: 100, offset: 0 } }).then((res) => {
            const lignes = res.data?.membres ?? [];
            setMembres(lignes.map((m) => ({ id: m.user_id, nom: [m.prenom, m.nom].filter(Boolean).join(" ") || t({ en: "Account without a name", fr: "Compte sans nom" }) })));
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        lireLeJournalFiltre({
            ...fenetrePage(page),
            ...(membreChoisi ? { membre: Number(membreChoisi) } : {}),
            ...(espaceChoisi ? { organization_id: Number(espaceChoisi) } : {}),
            ...(typeChoisi ? { action: typeChoisi } : {}),
            ...(porteChoisie ? { origine: porteChoisie as "ecran" | "api" | "mcp" } : {}),
        }).then((res) => {
            if (res.error || !res.data) {
                notifier.echec({ fr: "Journal illisible. Rechargez la page.", en: "Could not load the journal. Reload the page." }, { erreur: res.error });
                return;
            }
            setDonnees({ lignes: res.data.lignes, total: res.data.total });
        });
    }, [page, t, membreChoisi, espaceChoisi, typeChoisi, porteChoisie]);

    if (!donnees) return <EtatVide cas="chargement" />;

    const filtre = membreChoisi !== "" || espaceChoisi !== "" || typeChoisi !== "" || porteChoisie !== "";
    const libelleDuGeste = (a: string) => (GESTES[a] ? t(GESTES[a]) : a);
    const PORTES: Record<string, Texte> = { ecran: { en: "Screen", fr: "Écran" }, api: { en: "API", fr: "API" }, mcp: { en: "MCP", fr: "MCP" } };
    return (
        <div>
            <ReglageDureeDuJournal />
            <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="filtres-du-journal">
                <Liste
                    valeur={membreChoisi}
                    changer={(v) => {
                        setMembreChoisi(v);
                        setPage(0);
                    }}
                    vide={t({ en: "Everyone", fr: "Tout le monde" })}
                    options={membres.map((m) => ({ valeur: String(m.id), libelle: m.nom }))}
                    className="w-52"
                />
                <Liste
                    valeur={espaceChoisi}
                    changer={(v) => {
                        setEspaceChoisi(v);
                        setPage(0);
                    }}
                    vide={t({ en: "All spaces", fr: "Tous les espaces" })}
                    options={Object.entries(espaces).map(([id, nom]) => ({ valeur: id, libelle: nom }))}
                    className="w-52"
                />
                <Liste
                    valeur={typeChoisi}
                    changer={(v) => {
                        setTypeChoisi(v);
                        setPage(0);
                    }}
                    vide={t({ en: "All gestures", fr: "Tous les gestes" })}
                    options={types.map((a) => ({ valeur: a, libelle: libelleDuGeste(a) }))}
                    className="w-60"
                    libelle={t({ en: "Type of gesture", fr: "Type de geste" })}
                />
                <Liste
                    valeur={porteChoisie}
                    changer={(v) => {
                        setPorteChoisie(v);
                        setPage(0);
                    }}
                    vide={t({ en: "All doors", fr: "Toutes les portes" })}
                    options={Object.entries(PORTES).map(([id, libelle]) => ({ valeur: id, libelle: t(libelle) }))}
                    className="w-40"
                    libelle={t({ en: "Door", fr: "Porte" })}
                />
            </div>
            {donnees.total === 0 ? (
                filtre ? (
                    <EtatVide
                        cas="filtre"
                        recherche={[membres.find((m) => String(m.id) === membreChoisi)?.nom, espaces[Number(espaceChoisi)]].filter(Boolean).join(", ")}
                        effacer={() => {
                            setMembreChoisi("");
                            setEspaceChoisi("");
                            setTypeChoisi("");
                            setPorteChoisie("");
                            setPage(0);
                        }}
                    />
                ) : (
                    <EtatVide cas="premier" icone={ScrollText} titre={t({ en: "Nothing written yet", fr: "Rien d'écrit pour l'instant" })} />
                )
            ) : (
                <Paginee total={donnees.total} page={page} changerPage={setPage}>
                    <Tableau
                        colonnes={[
                            { titre: t({ en: "When", fr: "Quand" }) },
                            { titre: t({ en: "Who", fr: "Qui" }) },
                            { titre: t({ en: "What", fr: "Quoi" }) },
                            { titre: t({ en: "Door", fr: "Porte" }) },
                            { titre: t({ en: "Space", fr: "Espace" }), droite: true },
                        ]}
                    >
                        {donnees.lignes.map((l) => (
                            <Ligne key={l.id}>
                                <Cellule principale>{new Date(l.quand).toLocaleString()}</Cellule>
                                <Cellule>{quiEst(l, t({ en: "Account without a name", fr: "Compte sans nom" }))}</Cellule>
                                <Cellule>{GESTES[l.action] ? t(GESTES[l.action]) : l.action}</Cellule>
                                <Cellule>{l.origine ? t(PORTES[l.origine]) : "—"}</Cellule>
                                <Cellule droite>{l.organization_id != null ? (espaces[l.organization_id] ?? `#${l.organization_id}`) : "—"}</Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                </Paginee>
            )}
        </div>
    );
}
