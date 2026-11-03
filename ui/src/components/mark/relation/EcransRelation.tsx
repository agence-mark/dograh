"use client";

import { DoorOpen, MessageSquare, Star, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    ajouterNoteApiV1RelationClientsOrganizationIdNotesPost,
    ajouterTemoignageApiV1RelationClientsOrganizationIdTemoignagesPost,
    avisEtTemoignagesApiV1RelationAvisGet,
    listerEntreesApiV1RelationEntreesGet,
    listerNotesApiV1RelationClientsOrganizationIdNotesGet,
    maFileApiV1RelationFileGet,
    ouvrirSonPortailApiV1RelationClientsOrganizationIdEntreePost,
    reglerAccordApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdPatch,
    supprimerNoteApiV1RelationClientsOrganizationIdNotesNoteIdDelete,
    supprimerTemoignageApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdDelete,
} from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info, Marque } from "@/components/mark/studio/marques";
import { Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { BoiteMessages } from "./BoiteMessages";
import { lireClientsRelation } from "./lecture-clients";
import { ADRESSE_PORTAIL, lienDEntree, MarqueEtat, Pret, quand, useCharge } from "./commun";

const CONTENEUR = "mx-auto w-full max-w-6xl space-y-6 p-6";

// ---------------------------------------------------------------------- Accueil « Ma file » (E94)
export function AccueilRelation() {
    const { t } = useLangue();
    return (
        <Pret>
            <AccueilInterne t={t} />
        </Pret>
    );
}

function AccueilInterne({ t }: { t: ReturnType<typeof useLangue>["t"] }) {
    const file = useCharge(() => maFileApiV1RelationFileGet());
    const clients = useCharge(() => lireClientsRelation());
    return (
        <div className={CONTENEUR}>
            <TitrePage
                titre={t({ en: "Customer relations", fr: "Relation clients" })}
                info={t({
                    en: "Everything that waits for you, in one list. Call reports and outages live in To improve, per client.",
                    fr: "Tout ce qui attend, dans une seule liste. Les signalements sur un appel et les pannes vivent dans À améliorer, client par client.",
                })}
            />
            <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
                <div>
                    <TitreTableau titre={t({ en: "My queue", fr: "Ma file" })} />
                    {file.etat === "chargement" && <EtatVide cas="chargement" />}
                    {file.etat === "erreur" && <EtatVide cas="erreur" reessayer={file.recharger} />}
                    {file.donnees && file.donnees.length === 0 && (
                        <EtatVide cas="fait" titre={t({ en: "Nothing is waiting for the team", fr: "Rien n'attend l'équipe" })} donnee={clients.donnees ? `${clients.donnees.length} client${clients.donnees.length > 1 ? "s" : ""}` : undefined} />
                    )}
                    {file.donnees && file.donnees.length > 0 && (
                        <Tableau colonnes={[{ titre: t({ en: "Subject", fr: "Sujet" }) }, { titre: "Client" }, { titre: t({ en: "State", fr: "État" }) }, { titre: t({ en: "Updated", fr: "Mis à jour" }), droite: true }]}>
                            {file.donnees.map((f) => (
                                <Ligne key={f.id} href={`/relation/messages?fil=${f.id}`}>
                                    <Cellule principale sous={f.sorte === "demande_logiciel" ? f.logiciel : undefined}>{f.sujet}</Cellule>
                                    <Cellule>{f.client}</Cellule>
                                    <Cellule><MarqueEtat etat={f.etat} /></Cellule>
                                    <Cellule droite>{quand(f.modifie_le)}</Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    )}
                </div>
                <div>
                    <TitreTableau titre="Clients" />
                    {clients.donnees?.length === 0 && (
                        <EtatVide cas="premier" compact icone={Users} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />
                    )}
                    {clients.donnees?.map((c) => (
                        <Link key={c.id} href={`/relation/clients/${c.id}`} className="flex cursor-pointer items-center justify-between border-b py-2 text-sm hover:font-medium">
                            <span className="truncate">{c.nom}</span>
                            {c.non_lus > 0 && <Marque ton="plein">{c.non_lus}</Marque>}
                        </Link>
                    ))}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------- Messages (E92, E93)
export function EcranMessages({ fil }: { fil?: number | null }) {
    const { t } = useLangue();
    return (
        <Pret>
            <div className={CONTENEUR}>
                <TitrePage titre="Messages" info={t({ en: "Messages and software requests from your clients, one thread each.", fr: "Les messages et les demandes de logiciel de vos clients, un fil chacun." })} />
                <BoiteMessages filInitial={fil} />
            </div>
        </Pret>
    );
}

// ---------------------------------------------------------------------- Clients et fiche d'un client
export function EcranClients() {
    const { t } = useLangue();
    return (
        <Pret>
            <ClientsInterne t={t} />
        </Pret>
    );
}

function ClientsInterne({ t }: { t: ReturnType<typeof useLangue>["t"] }) {
    const { donnees, etat, recharger } = useCharge(() => lireClientsRelation());
    return (
        <div className={CONTENEUR}>
            <TitrePage titre="Clients" />
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees && donnees.length === 0 && <EtatVide cas="premier" icone={Users} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />}
            {donnees && donnees.length > 0 && (
                <Tableau colonnes={[{ titre: "Client" }, { titre: t({ en: "Open threads", fr: "Fils ouverts" }), droite: true }, { titre: t({ en: "Unread", fr: "Non lus" }), droite: true }, { titre: t({ en: "New requests", fr: "Demandes nouvelles" }), droite: true }]}>
                    {donnees.map((c) => (
                        <Ligne key={c.id} href={`/relation/clients/${c.id}`}>
                            <Cellule principale>{c.nom}</Cellule>
                            <Cellule droite>{c.ouverts}</Cellule>
                            <Cellule droite>{c.non_lus}</Cellule>
                            <Cellule droite>{c.demandes_nouvelles}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </div>
    );
}

type Onglet = "messages" | "notes" | "technique" | "entrees";

export function FicheClient({ id }: { id: number }) {
    return (
        <Pret>
            <FicheInterne id={id} />
        </Pret>
    );
}

function FicheInterne({ id }: { id: number }) {
    const { t } = useLangue();
    const [onglet, setOnglet] = useState<Onglet>("messages");
    const clients = useCharge(() => lireClientsRelation());
    const client = clients.donnees?.find((c) => c.id === id);
    const noms: Record<Onglet, string> = {
        messages: t({ en: "Messages and requests", fr: "Messages et demandes" }),
        notes: t({ en: "Internal notes", fr: "Notes internes" }),
        technique: t({ en: "Technical", fr: "Technique" }),
        entrees: t({ en: "Portal entries", fr: "Entrées au portail" }),
    };
    if (clients.etat === "chargement") return <div className={CONTENEUR}><EtatVide cas="chargement" /></div>;
    if (!client) return <div className={CONTENEUR}><EtatVide cas="erreur" reessayer={clients.recharger} /></div>;
    return (
        <div className={CONTENEUR}>
            <TitrePage
                titre={client.nom}
                action={
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" asChild>
                            <Link href={`/clients/${id}`}>{t({ en: "Open its space", fr: "Ouvrir son espace" })}</Link>
                        </Button>
                        <BoutonPortail organisation={id} />
                    </div>
                }
            />
            <Segmente valeur={noms[onglet]} options={Object.values(noms)} changer={(v) => setOnglet((Object.keys(noms) as Onglet[]).find((k) => noms[k] === v) ?? "messages")} />
            {onglet === "messages" && <BoiteMessages client={id} />}
            {onglet === "notes" && <NotesClient organisation={id} />}
            {onglet === "technique" && (
                <div className="space-y-2 text-sm">
                    <p>{t({ en: "Call reports and outages are kept in one place only.", fr: "Les signalements sur un appel et les pannes sont rangés à un seul endroit." })}</p>
                    <Button variant="outline" size="sm" asChild>
                        <Link href={`/clients/${id}/a-ameliorer`}>{t({ en: "Open To improve", fr: "Ouvrir À améliorer" })}</Link>
                    </Button>
                </div>
            )}
            {onglet === "entrees" && <ListeEntrees client={client.nom} />}
        </div>
    );
}

/** « Ouvrir son portail » : un lien d'une minute, à usage unique. Sans adresse de portail réglée, le bouton dit pourquoi. */
function BoutonPortail({ organisation }: { organisation: number }) {
    const { t } = useLangue();
    const [envoi, setEnvoi] = useState(false);
    const ouvrir = async () => {
        setEnvoi(true);
        const res = await ouvrirSonPortailApiV1RelationClientsOrganizationIdEntreePost({ path: { organization_id: organisation }, body: {} });
        setEnvoi(false);
        if (!res.data) return notifier.echec({ fr: "Lien non créé. Réessayez.", en: "Link not created. Try again." }, { erreur: res.error });
        window.open(lienDEntree(res.data.jeton), "_blank", "noopener");
    };
    return (
        <span className="inline-flex items-center gap-1">
            <Button size="sm" disabled={!ADRESSE_PORTAIL || envoi} onClick={ouvrir}>
                <DoorOpen className="size-4" /> {t({ en: "Open its portal", fr: "Ouvrir son portail" })}
            </Button>
            {!ADRESSE_PORTAIL && <Info>{t({ en: "The portal address is not set (NEXT_PUBLIC_PORTAIL_URL).", fr: "L'adresse du portail n'est pas réglée (NEXT_PUBLIC_PORTAIL_URL)." })}</Info>}
        </span>
    );
}

function NotesClient({ organisation }: { organisation: number }) {
    const { t } = useLangue();
    const { donnees, etat, recharger } = useCharge(() => listerNotesApiV1RelationClientsOrganizationIdNotesGet({ path: { organization_id: organisation } }));
    const [texte, setTexte] = useState("");
    const ajouter = async () => {
        const res = await ajouterNoteApiV1RelationClientsOrganizationIdNotesPost({ path: { organization_id: organisation }, body: { texte } });
        if (res.error) return notifier.echec({ fr: "Note non enregistrée. Réessayez.", en: "Note not saved. Try again." }, { erreur: res.error });
        setTexte("");
        recharger();
    };
    const retirer = async (noteId: number) => {
        const res = await supprimerNoteApiV1RelationClientsOrganizationIdNotesNoteIdDelete({ path: { organization_id: organisation, note_id: noteId } });
        if (res.error) return notifier.echec({ fr: "Opération impossible. Réessayez.", en: "Could not complete. Try again." }, { erreur: res.error });
        recharger();
    };
    return (
        <div className="space-y-4">
            <div className="flex items-start gap-2">
                <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} rows={2} />
                <Button size="sm" disabled={!texte.trim()} onClick={ajouter}>{t({ en: "Add", fr: "Ajouter" })}</Button>
                <Info>{t({ en: "Never shown to the client.", fr: "Jamais montrées au client." })}</Info>
            </div>
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees?.length === 0 && <EtatVide cas="premier" icone={MessageSquare} titre={t({ en: "No note yet", fr: "Aucune note pour l'instant" })} />}
            <div className="divide-y">
                {donnees?.map((n) => (
                    <div key={n.id} className="flex items-start justify-between gap-3 py-2 text-sm">
                        <div>
                            <p className="text-xs text-muted-foreground">{n.auteur} · {quand(n.cree_le)}</p>
                            <p className="whitespace-pre-wrap">{n.texte}</p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => retirer(n.id)}>{t({ en: "Delete", fr: "Supprimer" })}</Button>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------- Entrées dans les portails
function ListeEntrees({ client }: { client?: string }) {
    const { t } = useLangue();
    const { donnees, etat, recharger } = useCharge(() => listerEntreesApiV1RelationEntreesGet());
    const lignes = (donnees ?? []).filter((e) => !client || e.client === client);
    if (etat === "chargement") return <EtatVide cas="chargement" />;
    if (etat === "erreur") return <EtatVide cas="erreur" reessayer={recharger} />;
    if (lignes.length === 0) return <EtatVide cas="premier" icone={DoorOpen} titre={t({ en: "No entry yet", fr: "Aucune entrée pour l'instant" })} />;
    return (
        <Paginee liste={lignes}>
            {(page) => (
                <Tableau colonnes={[{ titre: t({ en: "When", fr: "Quand" }) }, { titre: t({ en: "Who", fr: "Qui" }) }, ...(client ? [] : [{ titre: "Client" }]), { titre: t({ en: "Reason", fr: "Motif" }) }, { titre: t({ en: "Used", fr: "Utilisé" }) }]}>
                    {page.map((e) => (
                        <Ligne key={e.id}>
                            <Cellule principale>{quand(e.cree_le)}</Cellule>
                            <Cellule>{e.auteur}</Cellule>
                            {!client && <Cellule>{e.client}</Cellule>}
                            <Cellule>{e.motif ?? ""}</Cellule>
                            <Cellule>{e.utilise_le ? quand(e.utilise_le) : t({ en: "Not used", fr: "Non utilisé" })}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </Paginee>
    );
}

export function EcranEntrees() {
    const { t } = useLangue();
    return (
        <Pret>
            <div className={CONTENEUR}>
                <TitrePage
                    titre={t({ en: "Portal entries", fr: "Entrées dans les portails" })}
                    info={t({ en: "Each entry uses a one-minute, single-use link. The client's manager sees it too.", fr: "Chaque entrée passe par un lien d'une minute, à usage unique. Le dirigeant du client la voit aussi." })}
                />
                <ListeEntrees />
            </div>
        </Pret>
    );
}

// ---------------------------------------------------------------------- Avis et témoignages
export function EcranAvis() {
    const { t } = useLangue();
    return (
        <Pret>
            <AvisInterne t={t} />
        </Pret>
    );
}

function AvisInterne({ t }: { t: ReturnType<typeof useLangue>["t"] }) {
    const { donnees, etat, recharger } = useCharge(() => avisEtTemoignagesApiV1RelationAvisGet());
    return (
        <div className={CONTENEUR}>
            <TitrePage
                titre={t({ en: "Reviews and testimonials", fr: "Avis et témoignages" })}
                info={t({ en: "The average comes from the visitors' reviews on each client's site. A testimonial is publishable only with the client's agreement.", fr: "La moyenne vient des avis des visiteurs du site de chaque client. Un témoignage n'est publiable qu'avec l'accord du client." })}
            />
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees?.length === 0 && <EtatVide cas="premier" icone={Star} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />}
            {donnees?.map((c) => (
                <div key={c.organization_id} className="space-y-2 border-b pb-4">
                    <p className="flex items-center gap-2 font-medium">
                        {c.client}
                        <span className="text-sm font-normal text-muted-foreground">
                            {c.note !== null ? `${c.note} / 5 · ${c.avis} ${t({ en: "reviews", fr: "avis" })}` : t({ en: "No review", fr: "Aucun avis" })}
                        </span>
                    </p>
                    {c.temoignages.map((x) => (
                        <div key={x.id} className="flex items-start justify-between gap-3 text-sm">
                            <div>
                                <p>{x.texte}</p>
                                <p className="text-xs text-muted-foreground">{x.auteur}</p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                                <Marque ton={x.accord ? "succes" : "neutre"}>{x.accord ? t({ en: "Agreed", fr: "Accord donné" }) : t({ en: "No agreement", fr: "Sans accord" })}</Marque>
                                <Button variant="ghost" size="sm" onClick={async () => { await reglerAccordApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdPatch({ path: { organization_id: c.organization_id, temoignage_id: x.id }, body: { accord: !x.accord } }); recharger(); }}>
                                    {x.accord ? t({ en: "Withdraw", fr: "Retirer l'accord" }) : t({ en: "Mark agreed", fr: "Accord obtenu" })}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={async () => { await supprimerTemoignageApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdDelete({ path: { organization_id: c.organization_id, temoignage_id: x.id } }); recharger(); }}>
                                    {t({ en: "Delete", fr: "Supprimer" })}
                                </Button>
                            </div>
                        </div>
                    ))}
                    <AjoutTemoignage organisation={c.organization_id} fait={recharger} />
                </div>
            ))}
        </div>
    );
}

function AjoutTemoignage({ organisation, fait }: { organisation: number; fait: () => void }) {
    const { t } = useLangue();
    const [texte, setTexte] = useState("");
    const [auteur, setAuteur] = useState("");
    const ajouter = async () => {
        const res = await ajouterTemoignageApiV1RelationClientsOrganizationIdTemoignagesPost({ path: { organization_id: organisation }, body: { texte, auteur, accord: false } });
        if (res.error) return notifier.echec({ fr: "Témoignage non enregistré. Réessayez.", en: "Testimonial not saved. Try again." }, { erreur: res.error });
        setTexte("");
        setAuteur("");
        fait();
    };
    return (
        <div className="flex flex-wrap items-center gap-2">
            <Input className="min-w-64 flex-1" value={texte} onChange={(e) => setTexte(e.target.value)} placeholder={t({ en: "Testimonial", fr: "Témoignage" })} />
            <Input className="w-48" value={auteur} onChange={(e) => setAuteur(e.target.value)} placeholder={t({ en: "Author, role", fr: "Auteur, fonction" })} />
            <Button size="sm" disabled={!texte.trim() || !auteur.trim()} onClick={ajouter}>{t({ en: "Add", fr: "Ajouter" })}</Button>
        </div>
    );
}

