"use client";

/**
 * [.mark] Theme « Client data » (chantier l-agent-travaille, L3, B4 to B6; rangement validé le 06/10).
 *
 * The client's own Postgres database: its name (B4: the password is the installation's, never
 * typed here), its state, its schema version (B6), the last write, what Dograh refused in it,
 * and the retention durations. Its actions act at once (like the Developers theme, E6): create,
 * attach, detach, upgrade, resynchronize; the retention has its own button.
 */
import { Database } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getBaseClientApiV1OrganizationsBaseClientGet,
    postCreerApiV1OrganizationsBaseClientCreerPost,
    postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost,
    postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost,
    putBaseClientApiV1OrganizationsBaseClientPut,
    putConservationApiV1OrganizationsBaseClientConservationPut,
} from "@/client/sdk.gen";
import type { Conservation, EtatBaseClient } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { type ProprietesThemeOrganisation, useSignaler } from "./ThemesOrganisation";

export const TITRE_DONNEES: Texte = { en: "Client data", fr: "Données du client" };

const LIBELLES_TABLES: Record<string, Texte> = {
    appel: { en: "Calls", fr: "Appels" },
    demande: { en: "Requests", fr: "Demandes" },
    contact: { en: "Contacts (after their last activity)", fr: "Contacts (après leur dernière activité)" },
    action: { en: "Actions (mails, SMS…)", fr: "Actions (mails, SMS…)" },
    // [.mark] L4 (A8): 6 months by default, shorter if the client wants.
    verbatim: { en: "Transcripts (verbatim)", fr: "Transcriptions (verbatim)" },
};

export const useBaseClient = () => {
    const { user, loading: authLoading } = useAuth();
    const [etat, setEtat] = useState<EtatBaseClient | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getBaseClientApiV1OrganizationsBaseClientGet();
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "Client database state unreadable"));
            return;
        }
        setErreur(null);
        setEtat(reponse.data);
    }, []);
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);
    const agir = useCallback(async (action: () => Promise<{ data?: EtatBaseClient; error?: unknown; response?: Response }>, succes: string) => {
        setEnCours(true);
        setErreur(null);
        const reponse = await action();
        setEnCours(false);
        if (reponse.error || !reponse.data) {
            // 409: the name is taken (another organization's database, or one the server already has).
            setErreur(reponse.response?.status === 409 ? NOM_PRIS : detailFromError(reponse.error, "Action refused"));
            return false;
        }
        setEtat(reponse.data);
        toast.success(succes);
        return true;
    }, []);
    return { etat, erreur, enCours, relire, agir };
};

// [.mark] Revue 1 (cloisonnement): shown instead of the server's English detail.
const NOM_PRIS = "mark:nom-de-base-pris";
const MESSAGE_NOM_PRIS: Texte = {
    en: "This database name is taken: it belongs to another organization, or already exists on the server. Choose another name.",
    fr: "Ce nom de base est déjà pris : il appartient à une autre organisation, ou la base existe déjà sur le serveur. Choisissez un autre nom.",
};

export const ThemeDonneesClient = ({
    ouvert,
    onBasculer,
    signaler,
    base,
}: ProprietesThemeOrganisation & { base: ReturnType<typeof useBaseClient> }) => {
    const { t } = useLangue();
    const { etat, erreur, enCours, agir } = base;
    const [nom, setNom] = useState("");
    const [conservation, setConservation] = useState<Conservation[]>([]);
    useEffect(() => {
        setConservation(etat?.conservation ?? []);
    }, [etat]);

    const rattachee = Boolean(etat?.nom_base);
    // n° 317: a database whose connection account has no rights yet is upgraded too.
    const enRetard = rattachee && ((etat?.version != null && etat.version < etat.version_attendue) || !!etat?.a_mettre_a_niveau);
    const conservationModifiee = JSON.stringify(conservation) !== JSON.stringify(etat?.conservation ?? []);
    useSignaler("donnees", conservationModifiee, Boolean(etat?.refus?.length), signaler);

    const resume = !etat
        ? [t({ en: "Loading...", fr: "Chargement..." })]
        : rattachee
          ? [
                etat.nom_base ?? "",
                etat.joignable ? `v${etat.version ?? "?"}/${etat.version_attendue}` : t({ en: "not reachable", fr: "injoignable" }),
            ]
          : [t({ en: "No database attached", fr: "Aucune base rattachée" })];

    return (
        <Theme
            id="donnees"
            icone={Database}
            titre={TITRE_DONNEES}
            description={{
                en: "The client's own database: the source of its establishments, team and sentences, and where every call is written.",
                fr: "La base propre du client : la source de ses établissements, de son équipe et de ses phrases, où chaque appel s'écrit.",
            }}
            resume={resume}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={conservationModifiee}
            erreurs={[]}
        >
            {erreur && (
                <p className="text-sm text-destructive" role="alert" data-testid="erreur-base-client">
                    {erreur === NOM_PRIS ? t(MESSAGE_NOM_PRIS) : erreur}
                </p>
            )}
            {!etat ? (
                <p className="text-sm text-muted-foreground">{t({ en: "Loading...", fr: "Chargement..." })}</p>
            ) : (
                <>
                    <Intertitre id="donnees-base" titre={{ en: "Database", fr: "Base" }}>
                        {!etat.serveur_configure && (
                            <p className="text-sm text-destructive" data-testid="serveur-non-configure">
                                {t({
                                    en: "The clients' Postgres is not configured on this installation (MARK_BASES_CLIENTS_URL).",
                                    fr: "Le Postgres des clients n'est pas configuré sur cette installation (MARK_BASES_CLIENTS_URL).",
                                })}
                            </p>
                        )}
                        {rattachee ? (
                            <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_1fr]" data-testid="etat-base-client">
                                <dt className="text-muted-foreground">{t({ en: "Name", fr: "Nom" })}</dt>
                                <dd className="font-mono">{etat.nom_base}</dd>
                                <dt className="text-muted-foreground">{t({ en: "State", fr: "État" })}</dt>
                                <dd>{etat.joignable ? t({ en: "reachable", fr: "joignable" }) : `${t({ en: "not reachable", fr: "injoignable" })}${etat.erreur ? ` : ${etat.erreur}` : ""}`}</dd>
                                <dt className="text-muted-foreground">{t({ en: "Schema version", fr: "Version du schéma" })}</dt>
                                <dd>
                                    {etat.version ?? "—"} / {etat.version_attendue}
                                    {enRetard && <span className="ml-2 text-destructive">{t({ en: "behind", fr: "en retard" })}</span>}
                                </dd>
                                <dt className="text-muted-foreground">{t({ en: "Last write", fr: "Dernière écriture" })}</dt>
                                <dd>{etat.derniere_ecriture ? new Date(etat.derniere_ecriture).toLocaleString() : "—"}</dd>
                            </dl>
                        ) : (
                            <ChampReglage
                                cle="nom_base"
                                idControle="base-client-nom"
                                libelle={{ en: "Database name", fr: "Nom de la base" }}
                                aides={[
                                    {
                                        en: "Lower case letters, digits and underscores (« client_exemple »). The server and its password are the installation's, never typed here.",
                                        fr: "Minuscules, chiffres et tirets bas (« client_exemple »). Le serveur et son mot de passe sont ceux de l'installation, jamais saisis ici.",
                                    },
                                ]}
                            >
                                <Input id="base-client-nom" value={nom} placeholder="client_essai" onChange={(e) => setNom(e.target.value.trim())} />
                            </ChampReglage>
                        )}
                        <div className="flex flex-wrap gap-2">
                            {!rattachee && (
                                <>
                                    <Button
                                        size="sm"
                                        disabled={enCours || !nom || !etat.serveur_configure}
                                        data-testid="creer-base-client"
                                        onClick={() =>
                                            void agir(
                                                () => postCreerApiV1OrganizationsBaseClientCreerPost({ body: { nom_base: nom } }),
                                                t({ en: "Database created and attached", fr: "Base créée et rattachée" }),
                                            )
                                        }
                                    >
                                        {t({ en: "Create database", fr: "Créer la base" })}
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        disabled={enCours || !nom || !etat.serveur_configure}
                                        data-testid="rattacher-base-client"
                                        onClick={() =>
                                            void agir(
                                                () => putBaseClientApiV1OrganizationsBaseClientPut({ body: { nom_base: nom } }),
                                                t({ en: "Database attached", fr: "Base rattachée" }),
                                            )
                                        }
                                    >
                                        {t({ en: "Attach an existing database", fr: "Rattacher une base existante" })}
                                    </Button>
                                </>
                            )}
                            {rattachee && (
                                <>
                                    {enRetard && (
                                        <Button
                                            size="sm"
                                            disabled={enCours}
                                            data-testid="mettre-a-niveau-base-client"
                                            onClick={() =>
                                                void agir(
                                                    () => postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost(),
                                                    t({ en: "Database upgraded", fr: "Base mise à niveau" }),
                                                )
                                            }
                                        >
                                            {t({ en: "Upgrade", fr: "Mettre à niveau" })}
                                        </Button>
                                    )}
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        disabled={enCours}
                                        data-testid="tester-base-client"
                                        onClick={() =>
                                            void agir(
                                                () => postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost(),
                                                t({ en: "Tested: the calls read the database again", fr: "Testée : les appels relisent la base" }),
                                            )
                                        }
                                    >
                                        {t({ en: "Test and resynchronize", fr: "Tester et resynchroniser" })}
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        disabled={enCours}
                                        data-testid="detacher-base-client"
                                        onClick={() =>
                                            void agir(
                                                () => putBaseClientApiV1OrganizationsBaseClientPut({ body: { nom_base: null } }),
                                                t({ en: "Database detached", fr: "Base détachée" }),
                                            )
                                        }
                                    >
                                        {t({ en: "Detach", fr: "Détacher" })}
                                    </Button>
                                </>
                            )}
                        </div>
                        {(etat.refus ?? []).length > 0 && (
                            <div className="rounded border border-destructive/50 p-2 text-sm" data-testid="refus-base-client">
                                <p className="font-medium text-destructive">
                                    {t({ en: "Values in the database that Dograh refused (not used by the calls):", fr: "Valeurs de la base refusées par Dograh (non lues par les appels) :" })}
                                </p>
                                <ul className="list-disc pl-5">
                                    {(etat.refus ?? []).map((r, i) => (
                                        <li key={i}>{r}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </Intertitre>

                    {rattachee && etat.joignable && conservation.length > 0 && (
                        <Intertitre
                            id="donnees-conservation"
                            titre={{ en: "Retention", fr: "Conservation" }}
                            description={{
                                en: "How long each kind of data is kept before the nightly purge. The client is responsible for its data: these are defaults to have validated.",
                                fr: "Combien de temps chaque donnée est gardée avant la purge de nuit. Le client est responsable de ses données : ce sont des défauts à faire valider.",
                            }}
                        >
                            {conservation.map((ligne, i) => (
                                <ChampReglage
                                    key={ligne.table_nom}
                                    cle={ligne.table_nom}
                                    idControle={`conservation-${ligne.table_nom}`}
                                    libelle={LIBELLES_TABLES[ligne.table_nom] ?? { en: ligne.table_nom, fr: ligne.table_nom }}
                                    aides={[{ en: "In days, 1 to 3650.", fr: "En jours, de 1 à 3650." }]}
                                >
                                    <Input
                                        id={`conservation-${ligne.table_nom}`}
                                        type="number"
                                        min={1}
                                        max={3650}
                                        value={ligne.duree_jours}
                                        onChange={(e) =>
                                            setConservation((avant) =>
                                                avant.map((l, j) => (j === i ? { ...l, duree_jours: Number(e.target.value) } : l)),
                                            )
                                        }
                                    />
                                </ChampReglage>
                            ))}
                            <Button
                                size="sm"
                                disabled={enCours || !conservationModifiee || conservation.some((l) => !(l.duree_jours >= 1 && l.duree_jours <= 3650))}
                                data-testid="enregistrer-conservation"
                                onClick={() =>
                                    void agir(
                                        () => putConservationApiV1OrganizationsBaseClientConservationPut({ body: conservation }),
                                        t({ en: "Retention saved", fr: "Conservation enregistrée" }),
                                    )
                                }
                            >
                                {t({ en: "Save retention", fr: "Enregistrer la conservation" })}
                            </Button>
                        </Intertitre>
                    )}
                </>
            )}
        </Theme>
    );
};
