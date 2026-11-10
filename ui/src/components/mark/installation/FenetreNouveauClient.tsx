"use client";

/**
 * [.mark] Partie 3, sous-lot 9 (SE-5, O-2, § 5 du plan) : « Nouveau client » qui installe vraiment. Fenêtre CENTRÉE (exception
 * listée par `16-fenetres-panneau-ou-centrees.md`), reprise de la maquette (`app/mark/page.tsx`, `NouveauClient`, E14) : en-tête
 * « Étape n sur 9 » et sa barre, les étapes cochées une à une, l'étape fautive en rouge avec « Reprendre ».
 *
 * L'état vit sur le serveur (`/installations-client`) : la fenêtre ne fait que le lire et demander l'étape suivante. Chaque
 * étape appelle la route qui existe déjà ; fermer la fenêtre ne perd rien, l'installation se reprend (ici, ou depuis la liste
 * des clients). Les requêtes d'une installation partent avec l'organisation du client (en-tête contrôlé par le serveur).
 * L'étape 6 ouvre la fenêtre de création d'agent UNIQUE ; l'étape 8 dépense : elle demande une confirmation, montant affiché ;
 * l'étape 7 montre la clé du client UNE fois.
 */
import { AlertCircle, Check, Copy, Loader2, Minus, Plus, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
    demarrerUneInstallationApiV1InstallationsClientPost,
    executerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPost,
    getCatalogueApiV1ConnecteursCatalogueGet,
    installationCouranteApiV1InstallationsClientCouranteGet,
    installationsOuvertesApiV1InstallationsClientOuvertesGet,
    passerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPasserPost,
} from "@/client/sdk.gen";
import type { ConnecteurVue, DonneesEtape, EtapeVue, InstallationResume, InstallationVue } from "@/client/types.gen";
import { FenetreCreationAgent } from "@/components/mark/agent/FenetreCreationAgent";
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { EXEMPLE_HORAIRES } from "@/components/mark/SectionHorairesOuverture";
import { ENTETE_ORGANISATION, retenirEspace } from "@/lib/espaceCourant";

const T = {
    titre: { en: "New client", fr: "Nouveau client" },
    etapeSur: { en: "Step {n} of 9", fr: "Étape {n} sur 9" },
    termine: { en: "Installation finished", fr: "Installation terminée" },
    nomEntreprise: { en: "Company name", fr: "Nom de l'entreprise" },
    nomRequis: { en: "Give the company name.", fr: "Donnez le nom de l'entreprise." },
    identifiant: { en: "Identifier", fr: "Identifiant" },
    identifiantAide: {
        en: "Lower case letters, digits and hyphens; it never changes.",
        fr: "Lettres minuscules, chiffres et tirets ; il ne change plus.",
    },
    identifiantInvalide: { en: "3 characters at least: lower case letters, digits, hyphens.", fr: "3 caractères au moins : minuscules, chiffres, tirets." },
    intro: {
        en: "A client holds its own agents, numbers and keys. Nothing is shared with the others. Each step uses the screen that already does it; you can stop and resume.",
        fr: "Un client a ses propres agents, numéros et clés. Rien n'est partagé avec les autres. Chaque étape passe par l'écran qui le fait déjà ; on peut s'arrêter et reprendre.",
    },
    enCoursAilleurs: { en: "Installations in progress", fr: "Installations en cours" },
    reprendre: { en: "Resume", fr: "Reprendre" },
    annuler: { en: "Cancel", fr: "Annuler" },
    fermer: { en: "Close", fr: "Fermer" },
    creerClient: { en: "Create the client", fr: "Créer le client" },
    passer: { en: "Skip this step", fr: "Passer cette étape" },
    passee: { en: "skipped", fr: "passée" },
    etapeFaite: { en: "Step done.", fr: "Étape faite." },
    etapePassee: { en: "Step skipped: it shows in the summary.", fr: "Étape passée : elle figure au récapitulatif." },
    clientCree: { en: "Client created. Next: its database.", fr: "Client créé. Suite : sa base." },
    echecGenerique: { en: "The step did not complete. Try again.", fr: "L'étape n'a pas abouti. Réessayez." },
    chargement: { en: "Loading the installation…", fr: "Lecture de l'installation…" },
    fermerSansEnregistrer: {
        en: "Your entries on this step are not saved. Close anyway? The installation itself stays, to resume.",
        fr: "Les saisies de cette étape ne sont pas enregistrées. Fermer quand même ? L'installation, elle, reste à reprendre.",
    },
    fermerQuandMeme: { en: "Close anyway", fr: "Fermer quand même" },
    rester: { en: "Stay", fr: "Rester" },
    // 2. base
    baseMode: { en: "Database", fr: "Base" },
    baseCreer: { en: "Create a new database (every update applied)", fr: "Créer une base neuve (toutes les mises à jour appliquées)" },
    baseRattacher: { en: "Attach a database that already exists", fr: "Rattacher une base qui existe déjà" },
    baseNom: { en: "Database name", fr: "Nom de la base" },
    baseFaire: { en: "Set up the database", fr: "Poser la base" },
    // 3. établissements
    etabNom: { en: "Establishment name", fr: "Nom de l'établissement" },
    etabHoraires: { en: "Opening hours", fr: "Horaires d'ouverture" },
    etabAjouter: { en: "Add an establishment", fr: "Ajouter un établissement" },
    etabFaire: { en: "Save the establishments", fr: "Enregistrer les établissements" },
    retirer: { en: "Remove", fr: "Retirer" },
    // 4. équipe
    prenom: { en: "First name", fr: "Prénom" },
    nomPersonne: { en: "Last name", fr: "Nom" },
    role: { en: "Role", fr: "Rôle" },
    personneAjouter: { en: "Add a person", fr: "Ajouter une personne" },
    sujet: { en: "Subject", fr: "Sujet" },
    sujetAide: { en: "E.g. Quote, Breakdown", fr: "Ex. Devis, Panne" },
    destinataire: { en: "Recipient", fr: "Destinataire" },
    sujetAjouter: { en: "Add a subject", fr: "Ajouter un sujet" },
    equipeFaire: { en: "Save the team", fr: "Enregistrer l'équipe" },
    personnes: { en: "People", fr: "Personnes" },
    sujets: { en: "Subjects", fr: "Sujets" },
    // 5. logiciels
    logicielsAide: {
        en: "The client authorizes each software from its portal; nothing connects without that gesture.",
        fr: "Le client autorise chaque logiciel depuis son portail ; rien ne se branche sans ce geste.",
    },
    logicielsFaire: { en: "Propose the software", fr: "Proposer les logiciels" },
    aucunLogiciel: { en: "No software in the catalogue.", fr: "Aucun logiciel au catalogue." },
    // 6. agent
    agentCreer: { en: "Create the agent", fr: "Créer l'agent" },
    agentAide: {
        en: "The single creation window opens for this client: structure, brain, starting point. The agent gets its « Main » branch.",
        fr: "La fenêtre de création unique s'ouvre pour ce client : structure, cerveau, point de départ. L'agent reçoit sa branche « Principale ».",
    },
    agentRetenir: { en: "Keep this agent", fr: "Retenir cet agent" },
    agentExistant: { en: "This client already has agents:", fr: "Ce client a déjà des agents :" },
    // 7. clé
    cleAide: {
        en: "A key the client's portal uses to reach the fork. Created by you, shown only once: copy the record for the portal now.",
        fr: "La clé avec laquelle le portail du client joint le fork. Créée par vous, montrée une seule fois : copiez la fiche du portail maintenant.",
    },
    cleFaire: { en: "Create the client's key", fr: "Créer la clé du client" },
    cleMontree: { en: "Shown only once. Copy it before closing.", fr: "Montrée une seule fois. Copiez-la avant de fermer." },
    cleCopier: { en: "Copy the portal record", fr: "Copier la fiche du portail" },
    cleCopiee: { en: "Record copied.", fr: "Fiche copiée." },
    cleNonCopiee: { en: "Copy failed: select the text and copy it.", fr: "Copie impossible : sélectionnez le texte et copiez-le." },
    cleFaiteAvant: { en: "Key created (prefix {p}). It is not shown again.", fr: "Clé créée (préfixe {p}). Elle n'est plus montrée." },
    // 8. appels simulés
    appelsAide: {
        en: "A series of simulated calls on the agent's scenarios. It spends money: confirm the amount first.",
        fr: "Une série d'appels simulés sur les scénarios de l'agent. Elle dépense : confirmez le montant d'abord.",
    },
    appelsScenarios: { en: "{n} scenario(s)", fr: "{n} scénario(s)" },
    appelsMontant: { en: "estimated {m}", fr: "estimé {m}" },
    appelsInconnu: { en: "amount unknown until the first call, at most the cap {p}", fr: "montant inconnu avant le premier appel, au plus le plafond {p}" },
    appelsLancer: { en: "Run the simulated calls", fr: "Lancer les appels simulés" },
    appelsConfirmer: { en: "Confirm the spending", fr: "Confirmer la dépense" },
    appelsQuestion: { en: "This series spends money: {m}. Run it?", fr: "Cette série dépense : {m}. La lancer ?" },
    appelsLance: { en: "Series running: follow it in the agent's Tests.", fr: "Série lancée : suivez-la dans les Tests de l'agent." },
    // 9. récapitulatif
    recapFaire: { en: "Show the summary", fr: "Voir le récapitulatif" },
    recapPret: { en: "Ready to publish: {a} to do, {b} blocking", fr: "Prêt à publier : {a} à faire, {b} bloquant(s)" },
    recapBranche: { en: "Branch « {b} »", fr: "Branche « {b} »" },
    recapPassees: { en: "Skipped steps, to do later in Dograh:", fr: "Étapes passées, à faire plus tard dans Dograh :" },
    ouvrirAgent: { en: "Open the agent", fr: "Ouvrir l'agent" },
    ouvrirClient: { en: "Open the client", fr: "Ouvrir le client" },
    terminer: { en: "Finish", fr: "Terminer" },
} satisfies Record<string, Texte>;

const dire = (texte: string, valeurs: Record<string, string | number>) =>
    texte.replace(/\{(\w+)\}/g, (_, cle: string) => String(valeurs[cle] ?? ""));

/** « Plomberie Garnier » -> « client-plomberie-garnier » (comme le serveur le dérive). */
export function identifiantPropose(nom: string): string {
    const propre = nom
        .normalize("NFKD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 50);
    return propre ? `client-${propre}` : "";
}

const IDENTIFIANT = /^[a-z0-9][a-z0-9-]{2,59}$/;

type Refus = { code?: string; fr?: string; en?: string };
const refusDe = (erreur: unknown): Refus | null => {
    const detail = (erreur as { detail?: unknown } | null | undefined)?.detail;
    return detail && typeof detail === "object" && !Array.isArray(detail) ? (detail as Refus) : null;
};

type Etablissement = { nom: string; horaires_ouverture: string };
type Personne = { prenom: string; nom: string; role: string };
type Sujet = { libelle: string; destinataire: number };

/** Une puce d'état d'étape, comme la maquette : fait (coché), en cours (tourne), erreur (rouge), passée, à faire (rond vide). */
function Puce({ etat }: { etat: EtapeVue["etat"] }) {
    if (etat === "faite") return <Check className="size-4 shrink-0 text-(--etat-fait)" aria-hidden />;
    if (etat === "en_cours") return <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden />;
    if (etat === "erreur") return <AlertCircle className="size-4 shrink-0 text-(--marque-danger-texte)" aria-hidden />;
    if (etat === "passee") return <Minus className="size-4 shrink-0 text-muted-foreground" aria-hidden />;
    return <span className="size-4 shrink-0 rounded-full border" aria-hidden />;
}

export function FenetreNouveauClient({
    ouvert,
    onOuvert,
    organisationAReprendre = null,
}: {
    ouvert: boolean;
    onOuvert: (o: boolean) => void;
    /** Reprendre l'installation ouverte de ce client (liste des clients). */
    organisationAReprendre?: number | null;
}) {
    const { t, langue } = useLangue();
    const [installation, setInstallation] = useState<InstallationVue | null>(null);
    const [chargement, setChargement] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [ouvertes, setOuvertes] = useState<InstallationResume[]>([]);
    // Étape 1
    const [nom, setNom] = useState("");
    const [identifiant, setIdentifiant] = useState("");
    const [identifiantTouche, setIdentifiantTouche] = useState(false);
    const [nomTouche, setNomTouche] = useState(false);
    const [erreurDemarrer, setErreurDemarrer] = useState<string | null>(null);
    // Étapes 2 à 5
    const [modeBase, setModeBase] = useState<"creer" | "rattacher">("creer");
    const [nomBase, setNomBase] = useState("");
    const [etablissements, setEtablissements] = useState<Etablissement[]>([{ nom: "", horaires_ouverture: "" }]);
    const [personnes, setPersonnes] = useState<Personne[]>([{ prenom: "", nom: "", role: "" }]);
    const [sujets, setSujets] = useState<Sujet[]>([]);
    const [catalogue, setCatalogue] = useState<ConnecteurVue[]>([]);
    const [choisis, setChoisis] = useState<string[]>([]);
    const [saisie, setSaisie] = useState(false);
    // Étapes 6 à 9
    const [creationAgent, setCreationAgent] = useState(false);
    const [fiche, setFiche] = useState<Record<string, unknown> | null>(null);
    const [confirmerDepense, setConfirmerDepense] = useState(false);
    const [confirmerFermeture, setConfirmerFermeture] = useState(false);
    const [precisions, setPrecisions] = useState<string[]>([]);

    const organisation = installation?.organization_id ?? null;
    const entetes = useMemo(() => (organisation ? { [ENTETE_ORGANISATION]: String(organisation) } : undefined), [organisation]);
    const prochaine = installation?.prochaine ?? null;
    const etapeCourante = installation?.etapes.find((e) => e.numero === prochaine) ?? null;
    const terminee = installation?.etat === "terminee";

    const reinitialiser = () => {
        setInstallation(null);
        setNom("");
        setIdentifiant("");
        setIdentifiantTouche(false);
        setNomTouche(false);
        setErreurDemarrer(null);
        setModeBase("creer");
        setNomBase("");
        setEtablissements([{ nom: "", horaires_ouverture: "" }]);
        setPersonnes([{ prenom: "", nom: "", role: "" }]);
        setSujets([]);
        setChoisis([]);
        setSaisie(false);
        setFiche(null);
        setConfirmerDepense(false);
        setConfirmerFermeture(false);
    };

    const lireInstallation = useCallback(async (organisationId: number) => {
        setChargement(true);
        try {
            const r = await installationCouranteApiV1InstallationsClientCouranteGet({ headers: { [ENTETE_ORGANISATION]: String(organisationId) } });
            if (r.error || !r.data) {
                const refus = refusDe(r.error);
                notifier.echec(refus?.fr && refus.en ? { fr: refus.fr, en: refus.en } : T.echecGenerique, { erreur: r.error });
                return;
            }
            setInstallation(r.data);
        } finally {
            setChargement(false);
        }
    }, []);

    // À l'ouverture : une installation désignée se relit ; sinon, la liste de celles qui sont en cours (« Reprendre »).
    useEffect(() => {
        if (!ouvert) return;
        if (organisationAReprendre) {
            void lireInstallation(organisationAReprendre);
            return;
        }
        void installationsOuvertesApiV1InstallationsClientOuvertesGet().then((r) => setOuvertes(r.data ?? []));
    }, [ouvert, organisationAReprendre, lireInstallation]);

    // Étape 5 : le catalogue des logiciels du client, lu une fois l'étape atteinte.
    useEffect(() => {
        if (prochaine !== 5 || !entetes) return;
        void getCatalogueApiV1ConnecteursCatalogueGet({ headers: entetes }).then((r) => setCatalogue((r.data ?? []).filter((c) => !c.interne)));
    }, [prochaine, entetes]);

    // Une nouvelle étape se présente vide (on ne garde pas la saisie de la précédente pour la suivante).
    useEffect(() => {
        setSaisie(false);
        setConfirmerDepense(false);
        if (prochaine === 2 && installation) setNomBase((n) => n || identifiantPropose(installation.nom).replace(/^client-/, "client_").replace(/-/g, "_").slice(0, 63));
    }, [prochaine, installation]);

    const fermer = () => {
        if (saisie && !confirmerFermeture) {
            setConfirmerFermeture(true);
            return;
        }
        onOuvert(false);
        reinitialiser();
    };

    const demarrer = async () => {
        setNomTouche(true);
        setIdentifiantTouche(true);
        const propre = nom.trim();
        const ident = identifiant.trim() || identifiantPropose(propre);
        if (!propre || !IDENTIFIANT.test(ident)) return;
        setEnCours(true);
        setErreurDemarrer(null);
        try {
            const r = await demarrerUneInstallationApiV1InstallationsClientPost({ body: { nom: propre, identifiant: ident } });
            if (r.error || !r.data) {
                const refus = refusDe(r.error);
                // Identifiant pris : la faute est sous le champ ; tout autre refus, une notification.
                if (refus?.code === "nom_pris" && refus.fr && refus.en) setErreurDemarrer(t({ fr: refus.fr, en: refus.en }));
                else notifier.echec(refus?.fr && refus.en ? { fr: refus.fr, en: refus.en } : T.echecGenerique, { erreur: r.error });
                return;
            }
            setInstallation(r.data);
            setSaisie(false);
            notifier.succes(T.clientCree);
        } catch (erreur) {
            notifier.echec(T.echecGenerique, { erreur });
        } finally {
            setEnCours(false);
        }
    };

    const executer = async (numero: number, donnees: DonneesEtape = {}, confirmer = false) => {
        if (!entetes) return;
        setEnCours(true);
        try {
            const r = await executerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPost({
                path: { numero },
                headers: entetes,
                body: { donnees, confirmer },
            });
            if (r.error || !r.data) {
                const refus = refusDe(r.error);
                notifier.echec(refus?.fr && refus.en ? { fr: refus.fr, en: refus.en } : T.echecGenerique, { erreur: r.error });
                await lireInstallation(organisation as number);
                return;
            }
            setInstallation(r.data.installation);
            setPrecisions(r.data.echec?.precisions ?? []);
            if (r.data.echec) {
                notifier.echec({ fr: r.data.echec.fr, en: r.data.echec.en });
                return;
            }
            setSaisie(false);
            if (r.data.montre?.fiche_portail) setFiche(r.data.montre.fiche_portail as Record<string, unknown>);
            notifier.succes(numero === 8 ? T.appelsLance : T.etapeFaite);
        } catch (erreur) {
            notifier.echec(T.echecGenerique, { erreur });
        } finally {
            setEnCours(false);
        }
    };

    const passer = async (numero: number) => {
        if (!entetes) return;
        setEnCours(true);
        try {
            const r = await passerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPasserPost({ path: { numero }, headers: entetes });
            if (r.error || !r.data) {
                const refus = refusDe(r.error);
                notifier.echec(refus?.fr && refus.en ? { fr: refus.fr, en: refus.en } : T.echecGenerique, { erreur: r.error });
                return;
            }
            setInstallation(r.data);
            setSaisie(false);
            notifier.information(T.etapePassee);
        } finally {
            setEnCours(false);
        }
    };

    const copierFiche = async () => {
        try {
            await navigator.clipboard.writeText(JSON.stringify(fiche, null, 2));
            notifier.succes(T.cleCopiee);
        } catch {
            notifier.echec(T.cleNonCopiee);
        }
    };

    const montant = (n: number | null | undefined, devise: string) =>
        n == null ? "" : new Intl.NumberFormat(langue === "fr" ? "fr-FR" : "en-GB", { style: "currency", currency: devise || "USD" }).format(n);
    const estimation = installation?.estimation ?? null;
    const phraseDepense = estimation
        ? estimation.montant != null
            ? t({ fr: dire(T.appelsMontant.fr, { m: montant(estimation.montant, estimation.devise ?? "USD") }), en: dire(T.appelsMontant.en, { m: montant(estimation.montant, estimation.devise ?? "USD") }) })
            : t({ fr: dire(T.appelsInconnu.fr, { p: montant(estimation.plafond, estimation.devise ?? "USD") }), en: dire(T.appelsInconnu.en, { p: montant(estimation.plafond, estimation.devise ?? "USD") }) })
        : "";

    const sousTitre = terminee
        ? t(T.termine)
        : installation && etapeCourante
          ? `${t({ fr: dire(T.etapeSur.fr, { n: etapeCourante.numero }), en: dire(T.etapeSur.en, { n: etapeCourante.numero }) })} · ${t(etapeCourante.titre)}`
          : `${t({ fr: dire(T.etapeSur.fr, { n: 1 }), en: dire(T.etapeSur.en, { n: 1 }) })} · ${t({ fr: "Le client et son organisation", en: "The client and its organization" })}`;

    // --- le formulaire de l'étape courante ------------------------------------------------------------------------------
    const ligne = "grid gap-2 sm:grid-cols-[1fr_1fr_auto] items-end";
    const formulaire = () => {
        if (!etapeCourante || terminee) return null;
        const n = etapeCourante.numero;
        if (n === 2)
            return (
                <div className="space-y-3">
                    <div className="space-y-1.5">
                        <Label htmlFor="installation-base-mode">{t(T.baseMode)}</Label>
                        <ListeDeroulante id="installation-base-mode" value={modeBase} onChange={(e) => setModeBase(e.target.value as "creer" | "rattacher")} className="w-full">
                            <option value="creer">{t(T.baseCreer)}</option>
                            <option value="rattacher">{t(T.baseRattacher)}</option>
                        </ListeDeroulante>
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="installation-base-nom">{t(T.baseNom)}</Label>
                        <Input
                            id="installation-base-nom"
                            value={nomBase}
                            maxLength={63}
                            className="font-mono text-sm"
                            onChange={(e) => {
                                setNomBase(e.target.value);
                                setSaisie(true);
                            }}
                        />
                    </div>
                </div>
            );
        if (n === 3)
            return (
                <div className="space-y-3">
                    {etablissements.map((e, i) => (
                        <div key={i} className={ligne}>
                            <div className="space-y-1.5">
                                <Label htmlFor={`etab-nom-${i}`}>{t(T.etabNom)}</Label>
                                <Input
                                    id={`etab-nom-${i}`}
                                    value={e.nom}
                                    maxLength={100}
                                    onChange={(ev) => {
                                        setEtablissements((l) => l.map((x, j) => (j === i ? { ...x, nom: ev.target.value } : x)));
                                        setSaisie(true);
                                    }}
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor={`etab-horaires-${i}`}>{t(T.etabHoraires)}</Label>
                                <Textarea
                                    id={`etab-horaires-${i}`}
                                    value={e.horaires_ouverture}
                                    maxLength={500}
                                    rows={3}
                                    className="min-h-16 text-sm"
                                    placeholder={EXEMPLE_HORAIRES}
                                    onChange={(ev) => {
                                        setEtablissements((l) => l.map((x, j) => (j === i ? { ...x, horaires_ouverture: ev.target.value } : x)));
                                        setSaisie(true);
                                    }}
                                />
                            </div>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="cursor-pointer"
                                aria-label={t(T.retirer)}
                                disabled={etablissements.length === 1}
                                onClick={() => setEtablissements((l) => l.filter((_, j) => j !== i))}
                            >
                                <X className="size-4" />
                            </Button>
                        </div>
                    ))}
                    <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setEtablissements((l) => [...l, { nom: "", horaires_ouverture: "" }])}>
                        <Plus className="size-4" /> {t(T.etabAjouter)}
                    </Button>
                </div>
            );
        if (n === 4)
            return (
                <div className="space-y-4">
                    <p className="text-sm font-medium">{t(T.personnes)}</p>
                    {personnes.map((p, i) => (
                        <div key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
                            {(["prenom", "nom", "role"] as const).map((champ) => (
                                <div key={champ} className="space-y-1.5">
                                    <Label htmlFor={`personne-${champ}-${i}`}>{t(champ === "prenom" ? T.prenom : champ === "nom" ? T.nomPersonne : T.role)}</Label>
                                    <Input
                                        id={`personne-${champ}-${i}`}
                                        value={p[champ]}
                                        maxLength={100}
                                        onChange={(ev) => {
                                            setPersonnes((l) => l.map((x, j) => (j === i ? { ...x, [champ]: ev.target.value } : x)));
                                            setSaisie(true);
                                        }}
                                    />
                                </div>
                            ))}
                            <Button
                                variant="ghost"
                                size="icon"
                                className="cursor-pointer"
                                aria-label={t(T.retirer)}
                                disabled={personnes.length === 1}
                                onClick={() => {
                                    setPersonnes((l) => l.filter((_, j) => j !== i));
                                    setSujets((l) => l.filter((s) => s.destinataire !== i).map((s) => ({ ...s, destinataire: s.destinataire > i ? s.destinataire - 1 : s.destinataire })));
                                }}
                            >
                                <X className="size-4" />
                            </Button>
                        </div>
                    ))}
                    <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setPersonnes((l) => [...l, { prenom: "", nom: "", role: "" }])}>
                        <Plus className="size-4" /> {t(T.personneAjouter)}
                    </Button>
                    <p className="pt-2 text-sm font-medium">{t(T.sujets)}</p>
                    {sujets.map((s, i) => (
                        <div key={i} className={ligne}>
                            <div className="space-y-1.5">
                                <Label htmlFor={`sujet-${i}`}>{t(T.sujet)}</Label>
                                <Input
                                    id={`sujet-${i}`}
                                    value={s.libelle}
                                    maxLength={100}
                                    placeholder={t(T.sujetAide)}
                                    onChange={(ev) => {
                                        setSujets((l) => l.map((x, j) => (j === i ? { ...x, libelle: ev.target.value } : x)));
                                        setSaisie(true);
                                    }}
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor={`sujet-dest-${i}`}>{t(T.destinataire)}</Label>
                                <ListeDeroulante
                                    id={`sujet-dest-${i}`}
                                    value={String(s.destinataire)}
                                    onChange={(ev) => setSujets((l) => l.map((x, j) => (j === i ? { ...x, destinataire: Number(ev.target.value) } : x)))}
                                    className="w-full"
                                >
                                    {personnes.map((p, j) => (
                                        <option key={j} value={String(j)}>
                                            {p.prenom.trim() || `#${j + 1}`}
                                        </option>
                                    ))}
                                </ListeDeroulante>
                            </div>
                            <Button variant="ghost" size="icon" className="cursor-pointer" aria-label={t(T.retirer)} onClick={() => setSujets((l) => l.filter((_, j) => j !== i))}>
                                <X className="size-4" />
                            </Button>
                        </div>
                    ))}
                    <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setSujets((l) => [...l, { libelle: "", destinataire: 0 }])}>
                        <Plus className="size-4" /> {t(T.sujetAjouter)}
                    </Button>
                </div>
            );
        if (n === 5)
            return (
                <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">{t(T.logicielsAide)}</p>
                    {catalogue.length === 0 ? (
                        <p className="text-sm text-muted-foreground">{t(T.aucunLogiciel)}</p>
                    ) : (
                        <div className="grid gap-2 sm:grid-cols-2">
                            {catalogue.map((c) => (
                                <label key={c.nom} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:font-medium">
                                    <input
                                        type="checkbox"
                                        className="size-4 cursor-pointer"
                                        checked={choisis.includes(c.nom)}
                                        onChange={(e) => {
                                            setChoisis((l) => (e.target.checked ? [...l, c.nom] : l.filter((x) => x !== c.nom)));
                                            setSaisie(true);
                                        }}
                                    />
                                    {c.libelle}
                                </label>
                            ))}
                        </div>
                    )}
                </div>
            );
        if (n === 6)
            return (
                <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">{t(T.agentAide)}</p>
                    {(installation?.agents_du_client ?? []).length > 0 && (
                        <div className="space-y-2" data-section="agents-du-client">
                            <p className="text-sm">{t(T.agentExistant)}</p>
                            {installation!.agents_du_client!.map((a) => (
                                <div key={a.id} className="flex items-center justify-between gap-3 text-sm">
                                    <span className="truncate">{a.nom}</span>
                                    <Button size="sm" variant="outline" className="cursor-pointer" disabled={enCours} onClick={() => void executer(6, { workflow_id: a.id })}>
                                        {t(T.agentRetenir)}
                                    </Button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            );
        if (n === 7) return <p className="text-sm text-muted-foreground">{t(T.cleAide)}</p>;
        if (n === 8)
            return (
                <div className="space-y-3" data-section="depense">
                    <p className="text-sm text-muted-foreground">{t(T.appelsAide)}</p>
                    {estimation && (
                        <p className="text-sm">
                            {t({ fr: dire(T.appelsScenarios.fr, { n: estimation.scenarios }), en: dire(T.appelsScenarios.en, { n: estimation.scenarios }) })} · {phraseDepense}
                        </p>
                    )}
                    {confirmerDepense && (
                        <div role="alertdialog" aria-label={t(T.appelsConfirmer)} className="space-y-3 rounded-lg bg-muted/60 p-3">
                            <p className="text-sm font-medium">{t({ fr: dire(T.appelsQuestion.fr, { m: phraseDepense }), en: dire(T.appelsQuestion.en, { m: phraseDepense }) })}</p>
                            <div className="flex justify-end gap-2">
                                <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => setConfirmerDepense(false)}>
                                    {t(T.annuler)}
                                </Button>
                                <Button size="sm" className="cursor-pointer" disabled={enCours} onClick={() => void executer(8, {}, true)}>
                                    {t(T.appelsConfirmer)}
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            );
        return null;
    };

    // --- le bouton principal de l'étape courante -------------------------------------------------------------------------
    const actionPrincipale = (): { libelle: Texte; faire: () => void } | null => {
        if (!installation) return { libelle: T.creerClient, faire: () => void demarrer() };
        if (terminee) return { libelle: T.terminer, faire: () => fermer() };
        const n = prochaine;
        if (n === 2) return { libelle: T.baseFaire, faire: () => void executer(2, { mode: modeBase, nom_base: nomBase.trim() }) };
        if (n === 3)
            return {
                libelle: T.etabFaire,
                faire: () => void executer(3, { etablissements: etablissements.filter((e) => e.nom.trim()).map((e) => ({ nom: e.nom.trim(), horaires_ouverture: e.horaires_ouverture.trim() || null })) }),
            };
        if (n === 4) {
            const gardees = personnes.map((p, i) => ({ p, i })).filter(({ p }) => p.prenom.trim());
            const index = new Map(gardees.map(({ i }, k) => [i, k]));
            return {
                libelle: T.equipeFaire,
                faire: () =>
                    void executer(4, {
                        personnes: gardees.map(({ p }) => ({ prenom: p.prenom.trim(), nom: p.nom.trim() || null, role: p.role.trim() || null })),
                        sujets: sujets
                            .filter((s) => s.libelle.trim())
                            .map((s) => ({ libelle: s.libelle.trim(), destinataires: index.has(s.destinataire) ? [index.get(s.destinataire) as number] : [] })),
                    }),
            };
        }
        if (n === 5) return { libelle: T.logicielsFaire, faire: () => void executer(5, { propositions: choisis.map((c) => ({ connecteur: c, compte: installation.nom.slice(0, 60) })) }) };
        if (n === 6) return { libelle: T.agentCreer, faire: () => setCreationAgent(true) };
        if (n === 7) return { libelle: T.cleFaire, faire: () => void executer(7) };
        if (n === 8) return { libelle: T.appelsLancer, faire: () => setConfirmerDepense(true) };
        if (n === 9) return { libelle: T.recapFaire, faire: () => void executer(9) };
        return null;
    };
    const action = actionPrincipale();

    const nomInvalide = nomTouche && !nom.trim();
    const identEffectif = identifiant || identifiantPropose(nom);
    const identInvalide = identifiantTouche && !!nom.trim() && !IDENTIFIANT.test(identEffectif);
    const recap = installation?.etapes.find((e) => e.numero === 9)?.resultat as
        | { workflow_id?: number; branche?: string; pret_a_publier?: { a_faire?: number; bloquants?: number }; passees?: number[] }
        | undefined;
    const cle7 = installation?.etapes.find((e) => e.numero === 7);

    return (
        <>
            <Dialog centree open={ouvert && !creationAgent} onOpenChange={(o) => (o ? onOuvert(true) : fermer())}>
                <DialogContent className="flex max-h-[85vh] w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-xl" data-modale="nouveau-client">
                    <DialogHeader className="border-b px-6 pt-6 pb-4 text-left">
                        <DialogTitle className="text-xl">{t(T.titre)}</DialogTitle>
                        <DialogDescription>{installation ? `${installation.nom} · ${sousTitre}` : sousTitre}</DialogDescription>
                        <div className="flex gap-1.5 pt-2" aria-hidden>
                            {Array.from({ length: 9 }, (_, i) => (
                                <span key={i} className={`h-1 flex-1 rounded-full ${i < (terminee ? 9 : (prochaine ?? 1)) ? "bg-primary" : "bg-muted"}`} />
                            ))}
                        </div>
                    </DialogHeader>
                    <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
                        {chargement && (
                            <p className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Loader2 className="size-4 animate-spin" /> {t(T.chargement)}
                            </p>
                        )}
                        {!installation && !chargement && (
                            <>
                                {ouvertes.length > 0 && (
                                    <div className="space-y-2 rounded-lg bg-muted/50 px-4 py-3" data-section="installations-en-cours">
                                        <p className="text-sm font-medium">{t(T.enCoursAilleurs)}</p>
                                        {ouvertes.map((o) => (
                                            <div key={o.id} className="flex items-center justify-between gap-3 text-sm">
                                                <span className="flex min-w-0 items-center gap-2">
                                                    {o.erreur ? <AlertCircle className="size-4 shrink-0 text-(--marque-danger-texte)" aria-hidden /> : <span className="size-4 shrink-0 rounded-full border" aria-hidden />}
                                                    <span className="truncate">{o.nom}</span>
                                                    <span className="text-muted-foreground">· {o.faites}/9</span>
                                                </span>
                                                <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => void lireInstallation(o.organization_id)}>
                                                    {t(T.reprendre)}
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                <p className="text-sm text-muted-foreground">{t(T.intro)}</p>
                                <div className="space-y-1.5">
                                    <Label htmlFor="nouveau-client-nom">{t(T.nomEntreprise)}</Label>
                                    <Input
                                        id="nouveau-client-nom"
                                        value={nom}
                                        maxLength={100}
                                        placeholder={t({ fr: "Ex. Plomberie Garnier", en: "E.g. Garnier Plumbing" })}
                                        autoComplete="off"
                                        aria-invalid={nomInvalide}
                                        aria-describedby={nomInvalide ? "nouveau-client-nom-erreur" : undefined}
                                        onChange={(e) => {
                                            setNom(e.target.value);
                                            setSaisie(true);
                                        }}
                                        onBlur={() => setNomTouche(true)}
                                        onKeyDown={(e) => e.key === "Enter" && void demarrer()}
                                    />
                                    <ErreurChamp id="nouveau-client-nom-erreur">{nomInvalide ? t(T.nomRequis) : null}</ErreurChamp>
                                </div>
                                <div className="space-y-1.5">
                                    <Label htmlFor="nouveau-client">{t(T.identifiant)}</Label>
                                    <Input
                                        id="nouveau-client"
                                        value={identEffectif}
                                        maxLength={60}
                                        className="font-mono text-sm"
                                        autoComplete="off"
                                        aria-invalid={identInvalide || !!erreurDemarrer}
                                        aria-describedby="nouveau-client-aide"
                                        onChange={(e) => {
                                            setIdentifiant(e.target.value);
                                            setErreurDemarrer(null);
                                        }}
                                        onBlur={() => setIdentifiantTouche(true)}
                                    />
                                    <p id="nouveau-client-aide" className="text-xs text-muted-foreground">
                                        {t(T.identifiantAide)}
                                    </p>
                                    <ErreurChamp>{identInvalide ? t(T.identifiantInvalide) : erreurDemarrer}</ErreurChamp>
                                </div>
                            </>
                        )}
                        {installation && (
                            <ul className="space-y-2.5 text-sm" data-section="etapes">
                                {installation.etapes.map((e) => {
                                    const courante = e.numero === prochaine && !terminee;
                                    return (
                                        <li key={e.numero} data-etape={e.numero} data-etat={e.etat} className="space-y-2">
                                            <div className={`flex items-center gap-2 ${e.etat === "a_faire" && !courante ? "text-muted-foreground" : ""}`}>
                                                <Puce etat={e.etat} />
                                                <span className={courante ? "font-medium" : ""}>{t(e.titre)}</span>
                                                {e.etat === "passee" && <span className="text-xs text-muted-foreground">· {t(T.passee)}</span>}
                                                {e.depense && <span className="text-xs text-muted-foreground">· {t({ fr: "dépense", en: "spends" })}</span>}
                                            </div>
                                            {e.etat === "erreur" && e.erreur && (
                                                <p role="alert" className="pl-6 text-sm text-(--marque-danger-texte)">
                                                    {t(e.erreur)}
                                                </p>
                                            )}
                                            {courante && e.etat === "erreur" && precisions.length > 0 && (
                                                <div className="pl-6" data-section="fautes-de-saisie">
                                                    {precisions.map((p) => (
                                                        <ErreurChamp key={p}>{p}</ErreurChamp>
                                                    ))}
                                                </div>
                                            )}
                                            {courante && <div className="pl-6">{formulaire()}</div>}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                        {fiche && (
                            <div className="space-y-2 rounded-lg bg-muted/60 p-3" data-section="fiche-portail">
                                <p className="text-sm font-medium">{t(T.cleMontree)}</p>
                                <pre className="max-h-40 overflow-auto rounded bg-background p-2 font-mono text-xs select-all">{JSON.stringify(fiche, null, 2)}</pre>
                                <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => void copierFiche()}>
                                    <Copy className="size-4" /> {t(T.cleCopier)}
                                </Button>
                            </div>
                        )}
                        {!fiche && cle7?.etat === "faite" && typeof cle7.resultat?.cle_prefixe === "string" && !terminee && (
                            <p className="text-xs text-muted-foreground">
                                {t({ fr: dire(T.cleFaiteAvant.fr, { p: cle7.resultat.cle_prefixe }), en: dire(T.cleFaiteAvant.en, { p: cle7.resultat.cle_prefixe }) })}
                            </p>
                        )}
                        {terminee && recap && (
                            <div className="space-y-2 text-sm" data-section="recapitulatif">
                                {recap.branche && <p>{t({ fr: dire(T.recapBranche.fr, { b: recap.branche }), en: dire(T.recapBranche.en, { b: recap.branche }) })}</p>}
                                {recap.pret_a_publier && (
                                    <p>
                                        {t({
                                            fr: dire(T.recapPret.fr, { a: recap.pret_a_publier.a_faire ?? 0, b: recap.pret_a_publier.bloquants ?? 0 }),
                                            en: dire(T.recapPret.en, { a: recap.pret_a_publier.a_faire ?? 0, b: recap.pret_a_publier.bloquants ?? 0 }),
                                        })}
                                    </p>
                                )}
                                {(recap.passees ?? []).length > 0 && (
                                    <p className="text-muted-foreground">
                                        {t(T.recapPassees)}{" "}
                                        {(recap.passees ?? []).map((n) => t(installation!.etapes.find((x) => x.numero === n)!.titre)).join(", ")}
                                    </p>
                                )}
                                <div className="flex flex-wrap gap-2 pt-1">
                                    {recap.workflow_id && (
                                        <Button size="sm" variant="outline" className="cursor-pointer" asChild>
                                            <Link href={`/agents/${recap.workflow_id}`} onClick={() => retenirEspace(`/clients/${organisation}`)}>
                                                {t(T.ouvrirAgent)}
                                            </Link>
                                        </Button>
                                    )}
                                    <Button size="sm" variant="outline" className="cursor-pointer" asChild>
                                        <Link href={`/clients/${organisation}`} onClick={() => retenirEspace(`/clients/${organisation}`)}>
                                            {t(T.ouvrirClient)}
                                        </Link>
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                    <DialogFooter className="flex-row flex-wrap items-center justify-between gap-2 border-t bg-background px-6 py-4 sm:justify-between">
                        {confirmerFermeture ? (
                            <div role="alertdialog" aria-label={t(T.fermerQuandMeme)} className="flex w-full flex-wrap items-center justify-between gap-2">
                                <p className="text-sm">{t(T.fermerSansEnregistrer)}</p>
                                <div className="flex gap-2">
                                    <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => setConfirmerFermeture(false)}>
                                        {t(T.rester)}
                                    </Button>
                                    <Button size="sm" className="cursor-pointer" onClick={fermer}>
                                        {t(T.fermerQuandMeme)}
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <>
                                <Button variant="outline" className="cursor-pointer" onClick={fermer} disabled={enCours}>
                                    {installation ? t(T.fermer) : t(T.annuler)}
                                </Button>
                                <div className="flex gap-2">
                                    {etapeCourante?.passable && !terminee && (
                                        <Button variant="ghost" className="cursor-pointer" disabled={enCours} onClick={() => void passer(etapeCourante.numero)}>
                                            {t(T.passer)}
                                        </Button>
                                    )}
                                    {action && !(prochaine === 8 && confirmerDepense) && (
                                        <Button className="cursor-pointer" disabled={enCours || chargement} onClick={action.faire}>
                                            {enCours && <Loader2 className="size-4 animate-spin" />}
                                            {etapeCourante?.etat === "erreur" ? t(T.reprendre) : t(action.libelle)}
                                        </Button>
                                    )}
                                </div>
                            </>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            {organisation !== null && (
                <FenetreCreationAgent
                    ouvert={creationAgent}
                    fermer={() => setCreationAgent(false)}
                    organisationId={organisation}
                    surCree={async (agent) => {
                        setCreationAgent(false);
                        await executer(6, { workflow_id: agent.workflowId });
                    }}
                />
            )}
        </>
    );
}
