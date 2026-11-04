"use client";

/**
 * [.mark] K4b : « Base du client » et « Conservation dans la base » comme la maquette (`ecrans-organisation.tsx`,
 * `EcranBase`), à la place des champs du thème « Données du client » (qui gardent leur forme hors de la page Base).
 * Mêmes routes, mêmes gestes ; l'état (la base, la conservation) reste dans `ThemeDonneesClient`.
 */
import { Database, RefreshCw } from "lucide-react";
import { useState } from "react";

import {
    postCreerApiV1OrganizationsBaseClientCreerPost,
    postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost,
    postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost,
    putBaseClientApiV1OrganizationsBaseClientPut,
} from "@/client/sdk.gen";
import type { Conservation, EtatBaseClient } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { LigneLue } from "../entreprise/section-lue";
import { type Texte, useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { FenetreLibre } from "../studio/fenetre-libre";
import { Info, PointEtat } from "../studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";

type Agir = (action: () => Promise<{ data?: EtatBaseClient; error?: unknown; response?: Response }>, succes: Texte) => Promise<boolean>;

export const LIBELLES_TABLES: Record<string, Texte> = {
    appel: { en: "Calls", fr: "Appels" },
    demande: { en: "Requests", fr: "Demandes" },
    contact: { en: "Contacts (after their last activity)", fr: "Contacts (après leur dernière activité)" },
    action: { en: "Actions (mails, SMS…)", fr: "Actions (mails, SMS…)" },
    // [.mark] L4 (A8): 6 months by default, shorter if the client wants.
    verbatim: { en: "Transcripts (verbatim)", fr: "Transcriptions (verbatim)" },
    evenement_portail: { en: "Portal events", fr: "Événements du portail" },
    verification: { en: "Caller verifications", fr: "Vérifications de l'appelant" },
};
/** L'ordre de la maquette (appels, demandes, contacts, actions, verbatim), puis le reste dans l'ordre du serveur. */
const ORDRE_TABLES = Object.keys(LIBELLES_TABLES);

export const BaseDuClient = ({ etat, enCours, agir, enRetard, erreur }: { etat: EtatBaseClient; enCours: boolean; agir: Agir; enRetard: boolean; erreur: React.ReactNode }) => {
    const { t } = useLangue();
    const [fenetre, setFenetre] = useState(false);
    const [nom, setNom] = useState("");
    // V4 : le « Geste » de la maquette (Créer une base / Rattacher une base existante), un seul « Enregistrer ».
    const [geste, setGeste] = useState<"creer" | "rattacher">("creer");
    const rattachee = Boolean(etat.nom_base);
    // L-4 : « Créer » une base quand une autre est rattachée détache l'ancienne (elle reste sur le serveur) : un second clic le confirme.
    const [confirmeCreation, setConfirmeCreation] = useState(false);
    const refus = etat.refus ?? [];
    const fermer = () => {
        setFenetre(false);
        setNom("");
        setGeste("creer");
        setConfirmeCreation(false);
    };
    const poser = async (action: Parameters<Agir>[0], succes: Texte) => {
        if (await agir(action, succes)) fermer();
    };
    return (
        <section id="donnees-base" data-groupe="donnees-base">
            <TitreTableau
                titre={t({ en: "Client database", fr: "Base du client" })}
                info={
                    <Info>
                        {t({
                            en: "One Postgres database per client. Create, attach, upgrade or detach; the server and its password are the installation's.",
                            fr: "Une base Postgres par client. Créer, rattacher, mettre à niveau ou détacher ; le serveur et son mot de passe sont ceux de l'installation.",
                        })}
                    </Info>
                }
                action={
                    <div className="flex items-center gap-2">
                        {rattachee && (
                            <>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={enCours}
                                    data-testid="tester-base-client"
                                    onClick={() =>
                                        void agir(
                                            () => postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost(),
                                            { en: "Tested: the calls read the database again.", fr: "Testée : les appels relisent la base." },
                                        )
                                    }
                                >
                                    <RefreshCw className="size-3.5" />
                                    {t({ en: "Test and resynchronize", fr: "Tester et resynchroniser" })}
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={enCours || !enRetard}
                                    title={enRetard ? undefined : t({ en: "The schema is up to date", fr: "Le schéma est à jour" })}
                                    data-testid="mettre-a-niveau-base-client"
                                    onClick={() =>
                                        void agir(
                                            () => postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost(),
                                            { en: "Database upgraded.", fr: "Base mise à niveau." },
                                        )
                                    }
                                >
                                    {t({ en: "Upgrade", fr: "Mettre à niveau" })}
                                </Button>
                            </>
                        )}
                        <Button variant={rattachee ? "ghost" : "outline"} size="sm" data-testid="changer-de-base" onClick={() => setFenetre(true)}>
                            {rattachee ? t({ en: "Change database", fr: "Changer de base" }) : t({ en: "Create or attach", fr: "Créer ou rattacher" })}
                        </Button>
                    </div>
                }
            />
            {rattachee ? (
                <div className="mt-4 divide-y border-t" data-testid="etat-base-client">
                    <LigneLue libelle={t({ en: "Name", fr: "Nom" })} valeur={<span className="font-mono text-xs">{etat.nom_base}</span>} />
                    <LigneLue
                        libelle={t({ en: "State", fr: "État" })}
                        valeur={
                            <PointEtat etat={etat.joignable ? "publie" : "panne"}>
                                {etat.joignable ? t({ en: "reachable", fr: "joignable" }) : `${t({ en: "not reachable", fr: "injoignable" })}${etat.erreur ? ` : ${etat.erreur}` : ""}`}
                            </PointEtat>
                        }
                    />
                    <LigneLue
                        libelle={t({ en: "Schema version", fr: "Version du schéma" })}
                        valeur={
                            <>
                                {etat.version ?? "—"} / {etat.version_attendue}
                                {enRetard ? (
                                    <span className="ml-2 text-destructive">{t({ en: "behind", fr: "en retard" })}</span>
                                ) : (
                                    <span className="text-muted-foreground"> · {t({ en: "up to date", fr: "à jour" })}</span>
                                )}
                            </>
                        }
                    />
                    <LigneLue libelle={t({ en: "Last write", fr: "Dernière écriture" })} valeur={etat.derniere_ecriture ? new Date(etat.derniere_ecriture).toLocaleString() : "—"} />
                    <LigneLue
                        libelle={t({ en: "Refused values", fr: "Valeurs refusées" })}
                        valeur={
                            refus.length === 0 ? (
                                <span className="flex items-center gap-1.5">
                                    {t({ en: "none", fr: "aucune" })}
                                    <Info>
                                        {t({
                                            en: "The values of the database that Dograh refuses (and that the calls therefore do not read) appear here with their reason.",
                                            fr: "Les valeurs de la base que Dograh refuse (et que les appels ne lisent donc pas) s'affichent ici avec leur raison.",
                                        })}
                                    </Info>
                                </span>
                            ) : (
                                <ul className="list-disc pl-5" data-testid="refus-base-client">
                                    {refus.map((r, i) => (
                                        <li key={i}>{r}</li>
                                    ))}
                                </ul>
                            )
                        }
                    />
                </div>
            ) : (
                <EtatVide cas="premier" icone={Database} titre={t({ en: "No database attached", fr: "Aucune base rattachée" })} />
            )}
            <FenetreLibre
                ouverte={fenetre}
                fermer={fermer}
                titre={rattachee ? t({ en: "Change database", fr: "Changer de base" }) : t({ en: "Create or attach a database", fr: "Créer ou rattacher une base" })}
                corps={
                    <div className="space-y-3 py-3.5">
                        <p className="text-sm font-medium">{t({ en: "Action", fr: "Geste" })}</p>
                        <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm" data-testid="geste-base-client">
                            {(
                                [
                                    ["creer", { en: "Create a database", fr: "Créer une base" }],
                                    ["rattacher", { en: "Attach an existing database", fr: "Rattacher une base existante" }],
                                ] as const
                            ).map(([id, libelle]) => (
                                <button
                                    key={id}
                                    type="button"
                                    aria-pressed={geste === id}
                                    data-geste={id}
                                    onClick={() => {
                                        setGeste(id);
                                        setConfirmeCreation(false);
                                    }}
                                    className={`cursor-pointer rounded-md px-3 py-1 ${geste === id ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                >
                                    {t(libelle)}
                                </button>
                            ))}
                        </span>
                        {erreur && (
                            <p className="text-sm text-destructive" role="alert" data-testid="erreur-base-client-fenetre">
                                {erreur}
                            </p>
                        )}
                        {!etat.serveur_configure && (
                            <p className="text-sm text-destructive" data-testid="serveur-non-configure" role="alert">
                                {t({
                                    en: "The clients' Postgres is not configured on this installation (MARK_BASES_CLIENTS_URL).",
                                    fr: "Le Postgres des clients n'est pas configuré sur cette installation (MARK_BASES_CLIENTS_URL).",
                                })}
                            </p>
                        )}
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t({ en: "Database name", fr: "Nom de la base" })}
                            <Info>
                                {t({
                                    en: "Lower case letters, digits and underscores (« client_exemple »). The server and its password are the installation's, never typed here.",
                                    fr: "Minuscules, chiffres et tirets bas (« client_exemple »). Le serveur et son mot de passe sont ceux de l'installation, jamais saisis ici.",
                                })}
                            </Info>
                        </p>
                        <Input
                            id="base-client-nom"
                            aria-label={t({ en: "Database name", fr: "Nom de la base" })}
                            value={nom}
                            placeholder="client_essai"
                            onChange={(e) => {
                                setNom(e.target.value.trim());
                                setConfirmeCreation(false);
                            }}
                        />
                        {confirmeCreation && (
                            <p className="text-sm" role="alert" data-testid="confirmer-changement-de-base">
                                {t({
                                    en: `The current database « ${etat.nom_base} » stays on the server: it is only detached from this client. Create « ${nom} » and attach it?`,
                                    fr: `L'ancienne base « ${etat.nom_base} » reste sur le serveur : elle est seulement détachée de ce client. Créer « ${nom} » et la rattacher ?`,
                                })}
                            </p>
                        )}
                    </div>
                }
                pied={
                    rattachee ? (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            disabled={enCours}
                            data-testid="detacher-base-client"
                            onClick={() =>
                                void poser(() => putBaseClientApiV1OrganizationsBaseClientPut({ body: { nom_base: null } }), { en: "Database detached.", fr: "Base détachée." })
                            }
                        >
                            {t({ en: "Detach", fr: "Détacher" })}
                        </Button>
                    ) : undefined
                }
                actions={
                    <>
                        <Button variant="outline" onClick={fermer}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button
                            disabled={enCours || !nom || !etat.serveur_configure}
                            data-testid="enregistrer-base-client"
                            onClick={() => {
                                if (geste === "creer" && rattachee && !confirmeCreation) return setConfirmeCreation(true);
                                void (geste === "creer"
                                    ? poser(() => postCreerApiV1OrganizationsBaseClientCreerPost({ body: { nom_base: nom } }), {
                                          en: "Database created and attached.",
                                          fr: "Base créée et rattachée.",
                                      })
                                    : poser(() => putBaseClientApiV1OrganizationsBaseClientPut({ body: { nom_base: nom } }), {
                                          en: "Database attached.",
                                          fr: "Base rattachée.",
                                      }));
                            }}
                        >
                            {confirmeCreation ? t({ en: "Yes, create and attach", fr: "Oui, créer et rattacher" }) : t({ en: "Save", fr: "Enregistrer" })}
                        </Button>
                    </>
                }
            />
        </section>
    );
};

/** La conservation par table, en tableau nu comme la maquette : donnée, jours, « Enregistrer » à droite du titre. */
export const TableauConservation = ({
    conservation,
    setConservation,
    bloque,
    enregistrer,
}: {
    conservation: Conservation[];
    setConservation: (f: (avant: Conservation[]) => Conservation[]) => void;
    bloque: boolean;
    enregistrer: () => void;
}) => {
    const { t } = useLangue();
    const libelle = (table: string) => (LIBELLES_TABLES[table] ? t(LIBELLES_TABLES[table]) : table);
    return (
        <section id="donnees-conservation" data-groupe="donnees-conservation">
            <TitreTableau
                titre={t({ en: "Retention in the database", fr: "Conservation dans la base" })}
                info={
                    <Info>
                        {t({
                            en: "How long each kind of data is kept before the nightly purge. The client is responsible for its data: these are defaults to have validated.",
                            fr: "Combien de temps chaque donnée est gardée avant la purge de nuit. Le client est responsable de ses données : ce sont des défauts à faire valider.",
                        })}
                    </Info>
                }
                action={
                    <Button size="sm" disabled={bloque} data-testid="enregistrer-conservation" onClick={enregistrer}>
                        {t({ en: "Save retention", fr: "Enregistrer la conservation" })}
                    </Button>
                }
            />
            <div className="mt-10">
            <Tableau
                colonnes={[
                    { titre: t({ en: "Data", fr: "Donnée" }) },
                    {
                        titre: (
                            <span className="inline-flex items-center gap-1.5">
                                {t({ en: "Days", fr: "Jours" })}
                                <Info>{t({ en: "From 1 to 3650.", fr: "De 1 à 3650." })}</Info>
                            </span>
                        ),
                        droite: true,
                    },
                ]}
            >
                {conservation
                    .map((ligne, i) => ({ ligne, i }))
                    .sort((a, b) => {
                        const rang = (n: string) => (ORDRE_TABLES.includes(n) ? ORDRE_TABLES.indexOf(n) : ORDRE_TABLES.length);
                        return rang(a.ligne.table_nom) - rang(b.ligne.table_nom);
                    })
                    .map(({ ligne, i }) => {
                    const valide = ligne.duree_jours >= 1 && ligne.duree_jours <= 3650;
                    return (
                        <Ligne key={ligne.table_nom}>
                            <Cellule principale>{libelle(ligne.table_nom)}</Cellule>
                            <td className="text-right">
                                <Input
                                    id={`conservation-${ligne.table_nom}`}
                                    type="number"
                                    min={1}
                                    max={3650}
                                    aria-label={libelle(ligne.table_nom)}
                                    aria-invalid={!valide}
                                    value={ligne.duree_jours}
                                    className={`ml-auto h-8 w-24 text-right ${valide ? "" : "border-(--pastille-urgente)"}`}
                                    onChange={(e) =>
                                        setConservation((avant) => avant.map((l, j) => (j === i ? { ...l, duree_jours: Number(e.target.value) } : l)))
                                    }
                                />
                            </td>
                        </Ligne>
                    );
                })}
            </Tableau>
            </div>
        </section>
    );
};
