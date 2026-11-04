"use client";

/**
 * [.mark] U3 sexies point 1 (E73, E75), puis K5 (fidélité à la maquette, E76, E77) : Intégrations › Logiciels.
 *
 * Comme la maquette : le tableau des comptes branchés (« Nos comptes de test » au Labo, « Comptes du client » chez un
 * client, où les propositions « À autoriser » sont des lignes comme les autres) ; le bouton « Catalogue » ouvre le catalogue
 * des logiciels dont les connecteurs sont codés ; une ligne ou une carte ouvre la fenêtre du logiciel : Configurer (les
 * comptes, « Brancher un compte de test » au Labo ou « Proposer au client » chez un client, Relancer, Copier le lien,
 * Débrancher), Actions (« Créer un outil »), À propos. Le logo officiel d'un éditeur s'ajoutera quand son fichier sera
 * versé : sans fichier, les initiales, jamais un logo redessiné. Aucun bouton « demander un logiciel » : outil interne.
 */
import { Copy, LayoutGrid, Link2, Plug, Plus, RefreshCw, Search, Unplug } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";

import {
    createToolApiV1ToolsPost,
    deleteConnexionApiV1ConnecteursConnexionsIntegrationDelete,
    deletePropositionApiV1ConnecteursPropositionsIdentifiantDelete,
    postLienPropositionApiV1ConnecteursPropositionsIdentifiantLienPost,
    postPropositionApiV1ConnecteursPropositionsPost,
    postRelanceApiV1ConnecteursPropositionsIdentifiantRelancerPost,
} from "@/client/sdk.gen";
import type { ConnecteurVue, ConnexionVue, PropositionConnecteur } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDate } from "@/lib/dateTime";

import { configParDefaut, type Connecteurs } from "../connecteurs/useConnecteurs";
import { type Texte, useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { BlocChamp, Champs, FenetreOnglets, LigneChamp, Section, TAILLE_FENETRE } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Info, Marque, PointEtat } from "../studio/marques";
import { espaceDe } from "../studio/navigation-studio";
import { Paginee } from "../studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";
import { ActionDePage } from "./action-de-page";
import { type Propositions } from "./usePropositions";

const initiales = (nom: string) =>
    nom
        .split(/\s+/)
        .map((m) => m[0] ?? "")
        .join("")
        .slice(0, 2)
        .toUpperCase();

export function Initiales({ nom, taille = 40 }: { nom: string; taille?: number }) {
    return (
        <span
            style={{ width: taille, height: taille, fontSize: taille * 0.36 }}
            className="inline-flex shrink-0 items-center justify-center rounded-lg border bg-muted font-semibold text-muted-foreground"
            aria-hidden
        >
            {initiales(nom)}
        </span>
    );
}

/** [.mark] E-F3-1 : l'état d'un logiciel du catalogue (À essayer, Prêt, À activer, Interne), comme la maquette. */
function useEtatLogiciel() {
    const { t } = useLangue();
    return (c: ConnecteurVue) =>
        c.etat === "a_activer"
            ? t({ en: "To activate", fr: "À activer" })
            : c.etat === "pret"
              ? t({ en: "Ready", fr: "Prêt" })
              : c.etat === "interne"
                ? t({ en: "Internal", fr: "Interne" })
                : t({ en: "To try", fr: "À essayer" });
}

const jour = (iso: string | null | undefined, langue: "fr" | "en") => (iso ? formatDate(iso, null, langue) : "–");

/** Une ligne du tableau des comptes : un compte branché, ou une proposition qui attend le client. */
type LigneCompte = {
    cle: string;
    connecteur: ConnecteurVue;
    compte: string;
    etat: "connecte" | "a_verifier" | "a_autoriser";
    par: string;
    outils: number;
    le: string;
};

const POINT = { connecte: "publie", a_verifier: "panne", a_autoriser: "attente" } as const;

function useLignes(connecteurs: Connecteurs, propositions: Propositions): LigneCompte[] {
    const { t, langue } = useLangue();
    const catalogue = connecteurs.catalogue ?? [];
    const lignes: LigneCompte[] = [];
    for (const x of connecteurs.etat?.connexions ?? []) {
        const c = catalogue.find((k) => k.integration === x.integration);
        if (!c) continue;
        lignes.push({
            cle: `${x.integration}/${x.connection_id}`,
            connecteur: c,
            compte: x.compte ?? x.connection_id,
            etat: x.erreurs ? "a_verifier" : "connecte",
            par: x.autorise_par ?? "–",
            outils: (x.utilise_par ?? []).length,
            le: jour(x.creee_le, langue),
        });
    }
    for (const p of propositions.liste ?? []) {
        if (p.etat !== "a_autoriser") continue;
        const c = catalogue.find((k) => k.nom === p.connecteur);
        if (!c) continue;
        lignes.push({
            cle: `proposition/${p.identifiant}`,
            connecteur: c,
            compte: p.compte,
            etat: "a_autoriser",
            par: p.propose_par ? t({ en: `proposed by ${p.propose_par}`, fr: `proposé par ${p.propose_par}` }) : t({ en: "proposed", fr: "proposé" }),
            outils: 0,
            le: jour(p.propose_le, langue),
        });
    }
    return lignes;
}

export function OngletLogiciels({ connecteurs, propositions }: { connecteurs: Connecteurs; propositions: Propositions }) {
    const { t } = useLangue();
    const { espace } = espaceDe(usePathname() ?? "/labo");
    const labo = espace === "labo";
    const [catalogueOuvert, setCatalogueOuvert] = useState(false);
    const [ouvert, setOuvert] = useState<string | null>(null);
    const lignes = useLignes(connecteurs, propositions);
    const etatLibelle = (e: LigneCompte["etat"]) =>
        e === "connecte" ? t({ en: "Connected", fr: "Connecté" }) : e === "a_verifier" ? t({ en: "To check", fr: "À vérifier" }) : t({ en: "To authorize", fr: "À autoriser" });
    if (connecteurs.erreur) return <EtatVide cas="erreur" reessayer={() => void connecteurs.relire()} />;
    if (!connecteurs.catalogue) return <EtatVide cas="chargement" />;
    const ouvertConnecteur = connecteurs.catalogue.find((c) => c.nom === ouvert);

    return (
        <>
            <TitreTableau
                titre={labo ? t({ en: "Our test accounts", fr: "Nos comptes de test" }) : t({ en: "The client's accounts", fr: "Comptes du client" })}
                info={
                    <Info>
                        {labo
                            ? t({
                                  en: ".mark's own accounts, connected for trials and benches. They never serve a client: every authorization belongs to an organization.",
                                  fr: "Les comptes de .mark, branchés pour les essais et les bancs. Ils ne servent jamais un client : chaque autorisation appartient à une organisation.",
                              })
                            : t({
                                  en: "The accounts the client authorized from its portal, and the ones we proposed. Every authorization belongs to its organization; .mark never sees a password or a key.",
                                  fr: "Les comptes que le client a autorisés depuis son portail, et ceux qu'on lui a proposés. Chaque autorisation appartient à son organisation ; .mark ne voit jamais son mot de passe ni sa clé.",
                              })}
                    </Info>
                }
            />
            <ActionDePage onglet="logiciels">
                <Button onClick={() => setCatalogueOuvert(true)}>
                    <LayoutGrid className="size-4" /> {t({ en: "Catalogue", fr: "Catalogue" })}
                </Button>
            </ActionDePage>
            {lignes.length === 0 ? (
                <EtatVide cas="premier" icone={Plug} titre={t({ en: "No software connected", fr: "Aucun logiciel branché" })} />
            ) : (
                <Paginee liste={lignes}>
                    {(page) => (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Software", fr: "Logiciel" }) },
                                { titre: t({ en: "State", fr: "État" }) },
                                { titre: labo ? t({ en: "Connected by", fr: "Branché par" }) : t({ en: "Authorized by", fr: "Autorisé par" }) },
                                { titre: t({ en: "Tools", fr: "Outils" }), droite: true },
                                { titre: t({ en: "Since", fr: "Depuis" }), droite: true },
                            ]}
                        >
                            {page.map((l) => (
                                <Ligne key={l.cle} onClick={() => setOuvert(l.connecteur.nom)}>
                                    <td className="py-3">
                                        <span className="flex items-center gap-3">
                                            <Initiales nom={l.connecteur.libelle} taille={32} />
                                            <span>
                                                <span className="block font-medium">{l.connecteur.libelle}</span>
                                                <span className="block text-xs text-muted-foreground">{l.compte}</span>
                                            </span>
                                        </span>
                                    </td>
                                    <Cellule>
                                        <PointEtat etat={POINT[l.etat]}>{etatLibelle(l.etat)}</PointEtat>
                                    </Cellule>
                                    <Cellule>{l.par}</Cellule>
                                    <Cellule droite>{l.outils}</Cellule>
                                    <Cellule droite>{l.le}</Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    )}
                </Paginee>
            )}
            {catalogueOuvert && (
                <FenetreCatalogue connecteurs={connecteurs} propositions={propositions} labo={labo} fermer={() => setCatalogueOuvert(false)} />
            )}
            {ouvertConnecteur && !catalogueOuvert && (
                <FenetreLogiciel connecteur={ouvertConnecteur} connecteurs={connecteurs} propositions={propositions} labo={labo} fermer={() => setOuvert(null)} />
            )}
        </>
    );
}

/** V4 : les catégories du catalogue, dans l'ordre du serveur (``CATEGORIES``) ; le serveur envoie l'identifiant français. */
const CATEGORIES_DU_CATALOGUE: Array<{ id: string; nom: Texte }> = [
    { id: "CRM", nom: { en: "CRM", fr: "CRM" } },
    { id: "Agenda", nom: { en: "Calendar", fr: "Agenda" } },
    { id: "Messages", nom: { en: "Messages", fr: "Messages" } },
    { id: "Données", nom: { en: "Data", fr: "Données" } },
    { id: "Support", nom: { en: "Support", fr: "Support" } },
    { id: "Interventions", nom: { en: "Field work", fr: "Interventions" } },
    { id: "Téléphonie", nom: { en: "Telephony", fr: "Téléphonie" } },
    { id: "Compta", nom: { en: "Accounting", fr: "Compta" } },
    { id: "Immobilier", nom: { en: "Real estate", fr: "Immobilier" } },
    { id: "Santé", nom: { en: "Health", fr: "Santé" } },
    { id: "Vétérinaire", nom: { en: "Veterinary", fr: "Vétérinaire" } },
    { id: "Nos connecteurs", nom: { en: "Our connectors", fr: "Nos connecteurs" } },
];

/** Le catalogue : une fenêtre de cartes, une recherche discrète dans l'en-tête ; une carte ouvre la fenêtre du logiciel par-dessus. */
function FenetreCatalogue({
    connecteurs,
    propositions,
    labo,
    fermer,
}: {
    connecteurs: Connecteurs;
    propositions: Propositions;
    labo: boolean;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const etatDe = useEtatLogiciel();
    const [q, setQ] = useState("");
    const [filtre, setFiltre] = useState("");
    const [ouvert, setOuvert] = useState<string | null>(null);
    const [categorie, setCategorie] = useState("");
    const catalogue = connecteurs.catalogue ?? [];
    const branche = (c: ConnecteurVue) => (connecteurs.etat?.connexions ?? []).some((x) => x.integration === c.integration);
    const nomDeCategorie = (id: string | null | undefined) => {
        const connue = CATEGORIES_DU_CATALOGUE.find((x) => x.id === id);
        return connue ? t(connue.nom) : (id ?? "");
    };
    // Les catégories qui ont au moins un logiciel, dans l'ordre du serveur ; le compte suit la recherche et le filtre.
    const dansLeFiltre = (c: ConnecteurVue) =>
        c.libelle.toLowerCase().includes(q.toLowerCase()) && (filtre === "" || (filtre === "branches" ? branche(c) : !branche(c) && !c.interne));
    const categories = CATEGORIES_DU_CATALOGUE.filter((x) => catalogue.some((c) => c.categorie === x.id));
    const liste = catalogue.filter((c) => dansLeFiltre(c) && (categorie === "" || c.categorie === categorie));
    const ouvertConnecteur = catalogue.find((c) => c.nom === ouvert);
    return (
        <Dialog open onOpenChange={(o) => !o && fermer()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className={`${TAILLE_FENETRE} flex flex-col gap-0 overflow-hidden p-0`}>
                <div className="flex shrink-0 items-center gap-4 border-b px-6 pt-5 pr-12 pb-4">
                    <div className="flex-1">
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            {t({ en: "Catalogue", fr: "Catalogue" })}
                            <Info>
                                {t({
                                    en: "The software our connectors can connect. A new software enters the catalogue when its connector is coded in the fork.",
                                    fr: "Les logiciels que nos connecteurs savent brancher. Un nouveau logiciel entre au catalogue quand son connecteur est codé dans le fork.",
                                })}
                            </Info>
                        </DialogTitle>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                            {catalogue.length} {t({ en: "software", fr: "logiciels" })}
                        </p>
                    </div>
                    <div className="relative w-56">
                        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            value={q}
                            onChange={(e) => {
                                setQ(e.target.value);
                                setCategorie("");
                            }}
                            aria-label={t({ en: "Search a software", fr: "Rechercher un logiciel" })}
                            placeholder={t({ en: "Search", fr: "Rechercher" })}
                            className="h-8 border-transparent bg-muted/60 pl-8 text-sm shadow-none focus-visible:bg-background"
                        />
                    </div>
                    <Liste
                        valeur={filtre}
                        changer={setFiltre}
                        vide={t({ en: "All", fr: "Tous" })}
                        options={[
                            { valeur: "branches", libelle: t({ en: "Connected", fr: "Branchés" }) },
                            { valeur: "non", libelle: t({ en: "Not connected", fr: "Non branchés" }) },
                        ]}
                        className="w-40"
                    />
                </div>
                <div className="grid min-h-0 flex-1 grid-cols-[200px_1fr]">
                    {categories.length > 0 && (
                        <nav className="space-y-0.5 overflow-auto border-r p-2" aria-label={t({ en: "Categories", fr: "Catégories" })} data-testid="categories-du-catalogue">
                            {[{ id: "", nom: { en: "All", fr: "Tous" } }, ...categories].map((x) => (
                                <button
                                    key={x.id}
                                    type="button"
                                    aria-pressed={categorie === x.id}
                                    data-categorie={x.id || "tous"}
                                    onClick={() => setCategorie(x.id)}
                                    className={`flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm ${categorie === x.id ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50 hover:font-medium hover:text-foreground"}`}
                                >
                                    <span className="flex-1">{t(x.nom)}</span>
                                    <span className="text-xs text-muted-foreground tabular-nums">{catalogue.filter((c) => dansLeFiltre(c) && (x.id === "" || c.categorie === x.id)).length}</span>
                                </button>
                            ))}
                        </nav>
                    )}
                <div className="min-h-0 overflow-auto p-5">
                    {liste.length === 0 ? (
                        catalogue.length === 0 ? (
                            <EtatVide cas="premier" icone={Plug} titre={t({ en: "No software", fr: "Aucun logiciel" })} compact />
                        ) : (
                            <EtatVide
                                cas="filtre"
                                recherche={q || (filtre === "branches" ? t({ en: "Connected", fr: "Branchés" }) : t({ en: "Not connected", fr: "Non branchés" }))}
                                effacer={() => {
                                    setQ("");
                                    setFiltre("");
                                }}
                                compact
                            />
                        )
                    ) : (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {liste.map((c) => (
                                <button
                                    key={c.nom}
                                    type="button"
                                    onClick={() => setOuvert(c.nom)}
                                    className="flex cursor-pointer flex-col rounded-xl border bg-background p-4 text-left transition-colors hover:border-foreground/40"
                                >
                                    <span className="flex items-start gap-3">
                                        <Initiales nom={c.libelle} />
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm leading-tight font-medium">{c.libelle}</span>
                                            <span className="mt-0.5 block text-xs text-muted-foreground">{nomDeCategorie(c.categorie) || c.integration}</span>
                                        </span>
                                    </span>
                                    <span className="mt-3 flex items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground">
                                        <span>
                                            {c.actions.length} {c.actions.length > 1 ? t({ en: "actions", fr: "actions" }) : t({ en: "action", fr: "action" })}
                                        </span>
                                        {branche(c) ? <PointEtat etat="publie">{t({ en: "Connected", fr: "Branché" })}</PointEtat> : <span>{etatDe(c)}</span>}
                                    </span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                </div>
                <div className="flex shrink-0 justify-end border-t px-6 py-3">
                    <Button onClick={fermer}>{t({ en: "Close", fr: "Fermer" })}</Button>
                </div>
                {ouvertConnecteur && (
                    <FenetreLogiciel connecteur={ouvertConnecteur} connecteurs={connecteurs} propositions={propositions} labo={labo} fermer={() => setOuvert(null)} />
                )}
            </DialogContent>
        </Dialog>
    );
}

/** Un geste qui touche un compte réel demande une confirmation en place : « Débrancher » puis « Confirmer ? ». */
function GesteConfirme({ libelle, confirmation, icone, onConfirme }: { libelle: string; confirmation: string; icone: React.ReactNode; onConfirme: () => void }) {
    const { t } = useLangue();
    const [demande, setDemande] = useState(false);
    if (!demande) {
        return (
            <Button variant="ghost" size="sm" onClick={() => setDemande(true)}>
                {icone} {libelle}
            </Button>
        );
    }
    return (
        <span className="inline-flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setDemande(false)}>
                {t({ en: "No", fr: "Non" })}
            </Button>
            <Button size="sm" onClick={onConfirme}>
                {confirmation}
            </Button>
        </span>
    );
}

function FenetreLogiciel({
    connecteur,
    connecteurs,
    propositions,
    labo,
    fermer,
}: {
    connecteur: ConnecteurVue;
    connecteurs: Connecteurs;
    propositions: Propositions;
    labo: boolean;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const etatDe = useEtatLogiciel();
    const libelles = { configurer: t({ en: "Configure", fr: "Configurer" }), actions: t({ en: "Actions", fr: "Actions" }), apropos: t({ en: "About", fr: "À propos" }) };
    const [onglet, setOnglet] = useState<keyof typeof libelles>(connecteur.interne ? "actions" : "configurer");
    const [brancher, setBrancher] = useState(false);
    const comptes: ConnexionVue[] = (connecteurs.etat?.connexions ?? []).filter((x) => x.integration === connecteur.integration);
    const attentes: PropositionConnecteur[] = (propositions.liste ?? []).filter((p) => p.connecteur === connecteur.nom && p.etat === "a_autoriser");
    const [compteDesOutils, setCompteDesOutils] = useState("");
    const nomDuCompte = (c: ConnexionVue) => c.compte ?? c.connection_id;

    const tester = async () => {
        await connecteurs.relire();
        notifier.succes({ fr: "Connexions relues.", en: "Connections read again." });
    };
    const debrancher = async (c: ConnexionVue) => {
        // suppression-confirmee : `GesteConfirme` : « Non / Confirmer » avant `debrancher`.
        const r = await deleteConnexionApiV1ConnecteursConnexionsIntegrationDelete({
            path: { integration: connecteur.integration },
            query: c.compte ? { compte: c.compte } : undefined,
        });
        if (r.error) return notifier.echec({ fr: "Logiciel non débranché. Réessayez.", en: "Not disconnected. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Compte débranché.", en: "Account disconnected." });
        await connecteurs.relire();
    };
    const relancer = async (p: PropositionConnecteur) => {
        const r = await postRelanceApiV1ConnecteursPropositionsIdentifiantRelancerPost({ path: { identifiant: p.identifiant } });
        if (r.error) return notifier.echec({ fr: "Relance impossible. Réessayez.", en: "Could not remind. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Le client a été relancé dans son portail.", en: "The client was reminded in its portal." });
        await propositions.relire();
    };
    const copierLeLien = async (p: PropositionConnecteur) => {
        const r = await postLienPropositionApiV1ConnecteursPropositionsIdentifiantLienPost({ path: { identifiant: p.identifiant } });
        if (r.error || !r.data?.lien) return notifier.echec({ fr: "Lien indisponible. Réessayez.", en: "Link unavailable. Try again." }, { erreur: r.error });
        void navigator.clipboard?.writeText(r.data.lien);
        notifier.succes({ fr: "Lien d'autorisation copié.", en: "Authorization link copied." });
    };
    const retirer = async (p: PropositionConnecteur) => {
        // suppression-confirmee : `GesteConfirme` : « Non / Confirmer » avant `retirer`.
        const r = await deletePropositionApiV1ConnecteursPropositionsIdentifiantDelete({ path: { identifiant: p.identifiant } });
        if (r.error) return notifier.echec({ fr: "Proposition non retirée. Réessayez.", en: "Proposal not withdrawn. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Proposition retirée.", en: "Proposal withdrawn." });
        await propositions.relire();
    };
    const creerUnOutil = async (action: string) => {
        const config = connecteurs.catalogue ? configParDefaut(connecteurs.catalogue, connecteur.nom, action) : null;
        if (!config) return;
        // Plusieurs comptes du même logiciel : l'outil garde le sien (sinon le seul compte, sans rien écrire).
        const compte = compteDesOutils || (comptes.length > 1 ? nomDuCompte(comptes[0]) : "");
        const r = await createToolApiV1ToolsPost({
            body: {
                name: `${connecteur.libelle} · ${action}`,
                category: "integration",
                definition: { schema_version: 1, type: "integration", config: compte ? { ...config, compte } : config },
            },
        });
        if (r.error) return notifier.echec({ fr: "Outil non créé. Réessayez.", en: "Tool not created. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Outil créé.", en: "Tool created." });
    };

    const ligneEtat = (
        <LigneChamp
            libelle={t({ en: "State", fr: "État" })}
            info={
                connecteur.etat === "pret"
                    ? t({ en: "Tried on a test account: ready to use.", fr: "Essayé sur un compte de test : prêt à servir." })
                    : t({
                          en: "Coded from the vendor's public documentation and proven on recorded answers. It is tried on a test account before being marked ready.",
                          fr: "Codé d'après la documentation publique de l'éditeur et prouvé sur des réponses enregistrées. Il est essayé sur un compte de test avant d'être marqué prêt.",
                      })
            }
        >
            <span className="text-sm">{etatDe(connecteur)}</span>
        </LigneChamp>
    );
    const brancheParNango = !connecteur.interne && connecteur.etat !== "a_activer";

    return (
        <FenetreOnglets
            fermer={fermer}
            titre={connecteur.libelle}
            sous={`${connecteur.integration} · ${etatDe(connecteur)}`}
            visuel={<Initiales nom={connecteur.libelle} />}
            onglets={Object.values(libelles)}
            onglet={libelles[onglet]}
            changerOnglet={(l) => setOnglet((Object.keys(libelles) as (keyof typeof libelles)[]).find((k) => libelles[k] === l) ?? "configurer")}
            valider={null}
        >
            {onglet === "configurer" &&
                (connecteur.etat === "a_activer" ? (
                    <Champs>
                        <LigneChamp
                            libelle={t({ en: "State", fr: "État" })}
                            info={t({
                                en: "The vendor opens its API on contract, in the client's name: the connector is coded for the first client of the sector who gives us the access.",
                                fr: "L'éditeur ouvre son API sur contrat, au nom du client : le connecteur se code au premier client du secteur qui nous ouvre l'accès.",
                            })}
                        >
                            <span className="text-sm">{etatDe(connecteur)}</span>
                        </LigneChamp>
                        {connecteur.editeur && (
                            <LigneChamp libelle={t({ en: "Vendor", fr: "Éditeur" })}>
                                <span className="text-sm">{connecteur.editeur}</span>
                            </LigneChamp>
                        )}
                        <LigneChamp
                            libelle={t({ en: "Access", fr: "Accès" })}
                            info={t({
                                en: "The contract with the vendor is signed in the client's name; the key received goes into the credentials.",
                                fr: "Le contrat avec l'éditeur se signe au nom du client ; la clé reçue va dans les identifiants.",
                            })}
                        >
                            <span className="text-sm">{t({ en: "API on contract", fr: "API sur contrat" })}</span>
                        </LigneChamp>
                    </Champs>
                ) : connecteur.interne ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Internal connector: nothing to connect.", fr: "Connecteur interne : rien à brancher." })}</p>
                ) : (
                    <>
                        <Champs>{ligneEtat}</Champs>
                        <Section
                            titre={labo ? t({ en: "Our test accounts", fr: "Nos comptes de test" }) : t({ en: "The client's accounts", fr: "Comptes du client" })}
                            info={t({
                                en: "Connected by an authorization (OAuth) managed by Nango: the client opens a link and authorizes the access; we never see a password.",
                                fr: "Branché par une autorisation (OAuth) gérée par Nango : le client ouvre un lien et autorise l'accès ; nous ne voyons jamais son mot de passe.",
                            })}
                            action={
                                // V2b : la raison d'un bouton grisé se lit au survol, jamais dans une phrase du corps de la fenêtre.
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <span id={labo && !connecteurs.etat?.nango_configure ? "connexions-nango-absent" : undefined}>
                                            <Button size="sm" disabled={!brancheParNango || (labo && !connecteurs.etat?.nango_configure)} onClick={() => setBrancher(true)}>
                                                <Plus className="size-4" />{" "}
                                                {labo ? t({ en: "Connect a test account", fr: "Brancher un compte de test" }) : t({ en: "Propose to the client", fr: "Proposer au client" })}
                                            </Button>
                                        </span>
                                    </TooltipTrigger>
                                    {labo && !connecteurs.etat?.nango_configure && (
                                        <TooltipContent className="max-w-xs text-xs leading-snug">
                                            {t({
                                                en: "No Nango on this installation (NANGO_URL, NANGO_SECRET_KEY): the integration tools fall back to their phrase.",
                                                fr: "Pas de Nango sur cette installation (NANGO_URL, NANGO_SECRET_KEY) : les outils d'intégration disent leur phrase de repli.",
                                            })}
                                        </TooltipContent>
                                    )}
                                </Tooltip>
                            }
                        >
                            {comptes.length === 0 && attentes.length === 0 ? (
                                <p className="py-2 text-sm text-muted-foreground">{t({ en: "No account connected in this space.", fr: "Aucun compte branché dans cet espace." })}</p>
                            ) : (
                                <Tableau
                                    colonnes={[
                                        { titre: t({ en: "Account", fr: "Compte" }) },
                                        { titre: t({ en: "State", fr: "État" }) },
                                        { titre: labo ? t({ en: "Connected by", fr: "Branché par" }) : t({ en: "Authorized by", fr: "Autorisé par" }) },
                                        { titre: t({ en: "Tools", fr: "Outils" }), droite: true },
                                        { titre: "" },
                                    ]}
                                >
                                    {comptes.map((c) => (
                                        <tr key={c.connection_id}>
                                            <Cellule principale>{nomDuCompte(c)}</Cellule>
                                            <Cellule>
                                                <PointEtat etat={c.erreurs ? "panne" : "publie"}>
                                                    {c.erreurs ? t({ en: "To check", fr: "À vérifier" }) : t({ en: "Connected", fr: "Connecté" })}
                                                </PointEtat>
                                            </Cellule>
                                            <Cellule>{c.autorise_par ?? "–"}</Cellule>
                                            <Cellule droite>{(c.utilise_par ?? []).length}</Cellule>
                                            <td className="py-2 pl-4 text-right whitespace-nowrap">
                                                <Button variant="ghost" size="sm" onClick={() => void tester()}>
                                                    <RefreshCw className="size-3.5" /> {t({ en: "Test", fr: "Tester" })}
                                                </Button>
                                                <GesteConfirme
                                                    libelle={t({ en: "Disconnect", fr: "Débrancher" })}
                                                    confirmation={t({ en: "Confirm", fr: "Confirmer" })}
                                                    icone={<Unplug className="size-3.5" />}
                                                    onConfirme={() => void debrancher(c)}
                                                />
                                            </td>
                                        </tr>
                                    ))}
                                    {attentes.map((p) => (
                                        <tr key={p.identifiant}>
                                            <Cellule principale>{p.compte}</Cellule>
                                            <Cellule>
                                                <PointEtat etat="attente">{t({ en: "To authorize", fr: "À autoriser" })}</PointEtat>
                                            </Cellule>
                                            <Cellule>{p.propose_par ? t({ en: `proposed by ${p.propose_par}`, fr: `proposé par ${p.propose_par}` }) : "–"}</Cellule>
                                            <Cellule droite>0</Cellule>
                                            <td className="py-2 pl-4 text-right whitespace-nowrap">
                                                <Button variant="ghost" size="sm" onClick={() => void relancer(p)}>
                                                    <RefreshCw className="size-3.5" /> {t({ en: "Remind", fr: "Relancer" })}
                                                </Button>
                                                <Button variant="ghost" size="sm" onClick={() => void copierLeLien(p)}>
                                                    <Copy className="size-3.5" /> {t({ en: "Copy the link", fr: "Copier le lien" })}
                                                </Button>
                                                <GesteConfirme
                                                    libelle={t({ en: "Withdraw", fr: "Retirer" })}
                                                    confirmation={t({ en: "Confirm", fr: "Confirmer" })}
                                                    icone={<Unplug className="size-3.5" />}
                                                    onConfirme={() => void retirer(p)}
                                                />
                                            </td>
                                        </tr>
                                    ))}
                                </Tableau>
                            )}
                        </Section>
                    </>
                ))}
            {onglet === "actions" && (
                <>
                    {comptes.length > 1 && (
                        <Champs>
                            <LigneChamp
                                libelle={t({ en: "Account of the tools created here", fr: "Compte des outils créés ici" })}
                                info={t({
                                    en: "Several accounts of this software are connected: a tool follows the one chosen here.",
                                    fr: "Plusieurs comptes de ce logiciel sont branchés : un outil suit celui choisi ici.",
                                })}
                            >
                                <Liste valeur={compteDesOutils || nomDuCompte(comptes[0])} changer={setCompteDesOutils} options={comptes.map(nomDuCompte)} className="w-64" />
                            </LigneChamp>
                        </Champs>
                    )}
                    <Tableau
                        colonnes={[
                            { titre: t({ en: "Action", fr: "Action" }) },
                            { titre: t({ en: "Access", fr: "Accès" }) },
                            {
                                titre: (
                                    <span className="inline-flex items-center gap-1.5">
                                        {t({ en: "Anticipable", fr: "Anticipable" })}
                                        <Info>{t({ en: "An action that reads can leave early, as soon as its parameters are known.", fr: "Une action qui lit peut partir en avance, dès que ses paramètres sont connus." })}</Info>
                                    </span>
                                ),
                            },
                            { titre: t({ en: "Parameters", fr: "Paramètres" }) },
                            { titre: "" },
                        ]}
                    >
                        {connecteur.actions.map((a) => (
                            <tr key={a.nom}>
                                <td className="py-3">
                                    <span className="block font-mono text-sm font-medium">{a.nom}</span>
                                    <span className="block text-xs text-muted-foreground">{a.description}</span>
                                </td>
                                <Cellule>{a.ecrit ? t({ en: "Writes", fr: "Écrit" }) : t({ en: "Reads", fr: "Lit" })}</Cellule>
                                <Cellule>{a.anticipable_permis ? t({ en: "Yes", fr: "Oui" }) : "–"}</Cellule>
                                <Cellule>
                                    <span className="font-mono text-xs">{a.parametres.map((p) => p.nom).join(", ") || "–"}</span>
                                </Cellule>
                                <td className="pl-4 text-right">
                                    <Button variant="ghost" size="sm" onClick={() => void creerUnOutil(a.nom)}>
                                        <Plus className="size-3.5" /> {t({ en: "Create a tool", fr: "Créer un outil" })}
                                    </Button>
                                </td>
                            </tr>
                        ))}
                    </Tableau>
                </>
            )}
            {onglet === "apropos" && (
                <Champs>
                    <LigneChamp libelle={t({ en: "Software key", fr: "Clé du logiciel" })}>
                        <span className="font-mono text-sm">{connecteur.integration}</span>
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Actions", fr: "Actions" })}>
                        <span className="text-sm">
                            {connecteur.actions.filter((a) => !a.ecrit).length} {t({ en: "that read", fr: "qui lisent" })} · {connecteur.actions.filter((a) => a.ecrit).length}{" "}
                            {t({ en: "that write", fr: "qui écrivent" })}
                        </span>
                    </LigneChamp>
                    <BlocChamp libelle={t({ en: "Tools that use it", fr: "Outils qui l'utilisent" })}>
                        {comptes.flatMap((c) => c.utilise_par ?? []).length === 0 ? (
                            <p className="text-sm text-muted-foreground">{t({ en: "No tool.", fr: "Aucun outil." })}</p>
                        ) : (
                            <ul className="text-sm">
                                {comptes
                                    .flatMap((c) => c.utilise_par ?? [])
                                    .map((o) => (
                                        <li key={o.tool_uuid} className="py-1 font-mono">
                                            {o.nom}
                                        </li>
                                    ))}
                            </ul>
                        )}
                    </BlocChamp>
                </Champs>
            )}
            {brancher && (
                <FenetreBrancher connecteur={connecteur} connecteurs={connecteurs} propositions={propositions} labo={labo} fermer={() => setBrancher(false)} />
            )}
        </FenetreOnglets>
    );
}

/**
 * Brancher un compte (E77). Au Labo : un compte de test de .mark, autorisé tout de suite (la page d'autorisation du
 * logiciel s'ouvre). Chez un client : « Proposer au client » ; la proposition arrive dans son portail, il autorise
 * lui-même ; « Copier un lien à la place » reste possible pour un client sans compte au portail.
 */
function FenetreBrancher({
    connecteur,
    connecteurs,
    propositions,
    labo,
    fermer,
}: {
    connecteur: ConnecteurVue;
    connecteurs: Connecteurs;
    propositions: Propositions;
    labo: boolean;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const [nom, setNom] = useState("");
    const [message, setMessage] = useState(
        t({ en: `For your agent to use ${connecteur.libelle}, authorize the access from your portal.`, fr: `Pour que votre agent puisse utiliser ${connecteur.libelle}, autorisez l'accès depuis votre portail.` }),
    );
    const [enCours, setEnCours] = useState(false);
    const compte = nom.trim() || (labo ? "compte de test .mark" : "nouveau compte");

    const lien = async () => {
        try {
            const r = await connecteurs.demanderLien([connecteur.nom], compte);
            return r.lien ?? null;
        } catch (e) {
            notifier.echec({ fr: "Lien d'autorisation indisponible. Réessayez.", en: "Authorization link unavailable. Try again." }, { erreur: e });
            return null;
        }
    };
    const autoriser = async () => {
        setEnCours(true);
        const adresse = await lien();
        setEnCours(false);
        if (!adresse) return;
        window.open(adresse, "_blank", "noopener");
        notifier.information({ fr: "Fenêtre d'autorisation ouverte.", en: "Authorization window opened." });
        fermer();
        await connecteurs.relire();
    };
    const proposer = async () => {
        setEnCours(true);
        const r = await postPropositionApiV1ConnecteursPropositionsPost({ body: { connecteur: connecteur.nom, compte, message: message.trim() } });
        setEnCours(false);
        if (r.error) return notifier.echec({ fr: "Proposition non envoyée. Réessayez.", en: "Proposal not sent. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Proposé : le client le voit dans son portail.", en: "Proposed: the client sees it in its portal." });
        await propositions.relire();
        fermer();
    };
    const copier = async () => {
        const adresse = await lien();
        if (!adresse) return;
        void navigator.clipboard?.writeText(adresse);
        notifier.succes({ fr: "Lien d'autorisation copié.", en: "Authorization link copied." });
    };

    return (
        <FenetreOnglets
            fermer={fermer}
            visuel={<Initiales nom={connecteur.libelle} />}
            titre={labo ? t({ en: `Connect ${connecteur.libelle}`, fr: `Brancher ${connecteur.libelle}` }) : t({ en: `Propose ${connecteur.libelle} to the client`, fr: `Proposer ${connecteur.libelle} au client` })}
            sous={
                labo
                    ? t({ en: "A .mark test account, for trials and benches.", fr: "Un compte de test de .mark, pour les essais et les bancs." })
                    : t({ en: "The client authorizes it itself, from its portal.", fr: "Le client autorise lui-même, depuis son portail." })
            }
            valider={labo ? t({ en: "Authorize now", fr: "Autoriser maintenant" }) : t({ en: "Propose to the client", fr: "Proposer au client" })}
            desactiver={enCours}
            onValider={() => void (labo ? autoriser() : proposer())}
            pied={
                !labo ? (
                    <Button variant="ghost" onClick={() => void copier()}>
                        <Link2 className="size-4" /> {t({ en: "Copy a link instead", fr: "Copier un lien à la place" })}
                    </Button>
                ) : undefined
            }
        >
            <Champs>
                <BlocChamp
                    libelle={t({ en: "Account name", fr: "Nom du compte" })}
                    info={t({
                        en: "To tell this account from the others of the same software (two Google calendars, for example). A tool chooses its account by this name.",
                        fr: "Pour reconnaître ce compte parmi les autres du même logiciel (deux agendas Google, par exemple). Un outil choisit son compte par ce nom.",
                    })}
                >
                    <Input
                        value={nom}
                        onChange={(e) => setNom(e.target.value)}
                        aria-label={t({ en: "Account name", fr: "Nom du compte" })}
                        placeholder={labo ? t({ en: "e.g. .mark test calendar", fr: "ex. agenda de test .mark" }) : t({ en: "e.g. technicians' calendar", fr: "ex. agenda des techniciens" })}
                    />
                </BlocChamp>
                {!labo && (
                    <BlocChamp
                        libelle={t({ en: "Message to the client", fr: "Message au client" })}
                        info={t({ en: "Shown with the proposal in its portal and in the notification.", fr: "Affiché avec la proposition dans son portail et dans la notification." })}
                    >
                        <Textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} aria-label={t({ en: "Message to the client", fr: "Message au client" })} />
                    </BlocChamp>
                )}
                {!labo && (
                    <LigneChamp
                        libelle={t({ en: "What the client does", fr: "Ce que fait le client" })}
                        info={t({
                            en: "He clicks « Authorize » in his portal: the software's login page opens, he signs in and accepts the access.",
                            fr: "Il clique « Autoriser » dans son portail : la page de connexion du logiciel s'ouvre, il se connecte et accepte l'accès.",
                        })}
                    >
                        <Marque>{t({ en: "authorizes", fr: "autorise" })}</Marque>
                    </LigneChamp>
                )}
            </Champs>
        </FenetreOnglets>
    );
}
