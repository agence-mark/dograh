"use client";

/**
 * [.mark] U3 sexies point 1 (E73, E75) : Intégrations › Logiciels.
 *
 * Le catalogue en cartes (le logo officiel d'un éditeur s'ajoutera quand son fichier sera versé : sans fichier, les
 * initiales, jamais un logo redessiné), recherche, filtre « Branchés », et la fenêtre d'un logiciel : Configurer
 * (comptes branchés : tester, nouveau lien, débrancher), Actions (« Créer un outil » sur une action), À propos.
 * Aucun bouton « demander un logiciel » : outil interne, on code le connecteur.
 */
import { Copy, Link2, Plug, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { createToolApiV1ToolsPost, deleteConnexionApiV1ConnecteursConnexionsIntegrationDelete } from "@/client/sdk.gen";
import type { ConnecteurVue, ConnexionVue } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { configParDefaut, type Connecteurs } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { BlocChamp, Champs, FenetreOnglets, LigneChamp } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Marque } from "../studio/marques";
import { Paginee } from "../studio/pagination";

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

export function OngletLogiciels({ connecteurs }: { connecteurs: Connecteurs }) {
    const { t } = useLangue();
    const [q, setQ] = useState("");
    const [filtre, setFiltre] = useState("");
    const [ouvert, setOuvert] = useState<string | null>(null);
    const catalogue = connecteurs.catalogue;
    if (connecteurs.erreur) return <EtatVide cas="erreur" reessayer={() => void connecteurs.relire()} />;
    if (!catalogue) return <EtatVide cas="chargement" />;

    const branche = (c: ConnecteurVue) => (connecteurs.etat?.connexions ?? []).some((x) => x.integration === c.integration);
    const liste = catalogue.filter(
        (c) =>
            c.libelle.toLowerCase().includes(q.toLowerCase()) &&
            (filtre === "" || (filtre === "branches" ? branche(c) : !branche(c) && !c.interne)),
    );
    const ouvertConnecteur = catalogue.find((c) => c.nom === ouvert);

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                <div className="relative w-full max-w-72">
                    <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder={t({ en: "Search a software", fr: "Rechercher un logiciel" })}
                        className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
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
                    className="w-44"
                    taille="default"
                />
            </div>
            {liste.length === 0 ? (
                catalogue.length === 0 ? (
                    <EtatVide cas="premier" icone={Plug} titre={t({ en: "No software", fr: "Aucun logiciel" })} />
                ) : (
                    <EtatVide
                        cas="filtre"
                        recherche={q || (filtre === "branches" ? t({ en: "Connected", fr: "Branchés" }) : t({ en: "Not connected", fr: "Non branchés" }))}
                        effacer={() => {
                            setQ("");
                            setFiltre("");
                        }}
                    />
                )
            ) : (
                <Paginee liste={liste}>
                    {(page) => (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {page.map((c) => (
                                <button
                                    key={c.nom}
                                    type="button"
                                    onClick={() => setOuvert(c.nom)}
                                    className="flex cursor-pointer items-center gap-3 rounded-xl border bg-background p-4 text-left transition-colors hover:border-foreground/40"
                                >
                                    <Initiales nom={c.libelle} />
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-sm font-medium">{c.libelle}</span>
                                        <span className="block text-xs text-muted-foreground">
                                            {c.interne
                                                ? t({ en: "Internal", fr: "Interne" })
                                                : branche(c)
                                                  ? t({ en: "Connected", fr: "Branché" })
                                                  : t({ en: "Not connected", fr: "Non branché" })}
                                            {" · "}
                                            {c.actions.length} {t({ en: "actions", fr: "actions" })}
                                        </span>
                                    </span>
                                </button>
                            ))}
                        </div>
                    )}
                </Paginee>
            )}
            {ouvertConnecteur && <FenetreLogiciel connecteur={ouvertConnecteur} connecteurs={connecteurs} fermer={() => setOuvert(null)} />}
        </div>
    );
}

function FenetreLogiciel({ connecteur, connecteurs, fermer }: { connecteur: ConnecteurVue; connecteurs: Connecteurs; fermer: () => void }) {
    const { t } = useLangue();
    const libelles = { configurer: t({ en: "Configure", fr: "Configurer" }), actions: t({ en: "Actions", fr: "Actions" }), apropos: t({ en: "About", fr: "À propos" }) };
    const [onglet, setOnglet] = useState<keyof typeof libelles>(connecteur.interne ? "actions" : "configurer");
    const [lien, setLien] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const comptes: ConnexionVue[] = (connecteurs.etat?.connexions ?? []).filter((x) => x.integration === connecteur.integration);

    const nouveauLien = async () => {
        try {
            const r = await connecteurs.demanderLien([connecteur.nom]);
            if (r.lien) setLien(r.lien);
        } catch (e) {
            notifier.echec({ fr: "Lien d'autorisation indisponible. Réessayez.", en: "Authorization link unavailable. Try again." }, { erreur: e });
        }
    };
    const tester = async () => {
        await connecteurs.relire();
        setMessage(t({ en: "Connections read again.", fr: "Connexions relues." }));
    };
    const debrancher = async () => {
        const r = await deleteConnexionApiV1ConnecteursConnexionsIntegrationDelete({ path: { integration: connecteur.integration } });
        if (r.error) return notifier.echec({ fr: "Logiciel non débranché. Réessayez.", en: "Not disconnected. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Logiciel débranché.", en: "Disconnected." });
        await connecteurs.relire();
    };
    const creerUnOutil = async (action: string) => {
        const config = connecteurs.catalogue ? configParDefaut(connecteurs.catalogue, connecteur.nom, action) : null;
        if (!config) return;
        const r = await createToolApiV1ToolsPost({
            body: { name: `${connecteur.libelle} · ${action}`, category: "integration", definition: { schema_version: 1, type: "integration", config } },
        });
        if (r.error) return notifier.echec({ fr: "Outil non créé. Réessayez.", en: "Tool not created. Try again." }, { erreur: r.error });
        notifier.succes({ fr: "Outil créé.", en: "Tool created." });
    };

    return (
        <FenetreOnglets
            fermer={fermer}
            titre={connecteur.libelle}
            sous={connecteur.integration}
            visuel={<Initiales nom={connecteur.libelle} />}
            onglets={Object.values(libelles)}
            onglet={libelles[onglet]}
            changerOnglet={(l) => setOnglet((Object.keys(libelles) as (keyof typeof libelles)[]).find((k) => libelles[k] === l) ?? "configurer")}
            valider={null}
        >
            {onglet === "configurer" &&
                (connecteur.interne ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Internal connector: nothing to connect.", fr: "Connecteur interne : rien à brancher." })}</p>
                ) : !connecteurs.etat?.nango_configure ? (
                    <p className="text-sm text-muted-foreground" id="connexions-nango-absent">
                        {t({
                            en: "No Nango on this installation (NANGO_URL, NANGO_SECRET_KEY): the integration tools fall back to their phrase.",
                            fr: "Pas de Nango sur cette installation (NANGO_URL, NANGO_SECRET_KEY) : les outils d'intégration disent leur phrase de repli.",
                        })}
                    </p>
                ) : (
                    <Champs>
                        {comptes.length === 0 && <p className="py-3 text-sm text-muted-foreground">{t({ en: "No account connected.", fr: "Aucun compte branché." })}</p>}
                        {comptes.map((c) => (
                            <LigneChamp
                                key={c.connection_id}
                                libelle={
                                    <span>
                                        {c.connection_id}
                                        <span className="block text-xs font-normal text-muted-foreground">
                                            {c.creee_le ?? ""}
                                            {c.erreurs ? ` · ${c.erreurs} ${t({ en: "error(s)", fr: "erreur(s)" })}` : ""}
                                        </span>
                                    </span>
                                }
                            >
                                <span className="inline-flex items-center gap-2">
                                    <Marque ton={c.erreurs ? "danger" : "succes"}>{c.erreurs ? t({ en: "To check", fr: "À vérifier" }) : t({ en: "Working", fr: "Fonctionne" })}</Marque>
                                    <Button variant="outline" size="sm" onClick={() => void tester()}>
                                        <RefreshCw className="size-3.5" /> {t({ en: "Test", fr: "Tester" })}
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={() => void debrancher()}>
                                        {t({ en: "Disconnect", fr: "Débrancher" })}
                                    </Button>
                                </span>
                            </LigneChamp>
                        ))}
                        {message && <p className="py-2 text-sm text-muted-foreground">{message}</p>}
                        <BlocChamp libelle={t({ en: "New account", fr: "Nouveau compte" })} info={t({ en: "A link to send to the client, who authorizes the access in the software.", fr: "Un lien à envoyer au client, qui autorise l'accès dans le logiciel." })}>
                            <Button variant="outline" size="sm" onClick={() => void nouveauLien()}>
                                <Link2 className="size-3.5" /> {comptes.length ? t({ en: "New authorization link", fr: "Nouveau lien d'autorisation" }) : t({ en: "Authorization link for the client", fr: "Lien d'autorisation pour le client" })}
                            </Button>
                            {lien && (
                                <div className="mt-2 flex items-center gap-2">
                                    <Input readOnly value={lien} className="font-mono text-xs" aria-label={t({ en: "Authorization link", fr: "Lien d'autorisation" })} />
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        aria-label={t({ en: "Copy the link", fr: "Copier le lien" })}
                                        onClick={() => {
                                            void navigator.clipboard?.writeText(lien);
                                            notifier.succes({ fr: "Lien copié.", en: "Link copied." });
                                        }}
                                    >
                                        <Copy className="size-3.5" />
                                    </Button>
                                </div>
                            )}
                        </BlocChamp>
                    </Champs>
                ))}
            {onglet === "actions" && (
                <Champs>
                    {connecteur.actions.map((a) => (
                        <LigneChamp
                            key={a.nom}
                            libelle={
                                <span>
                                    <span className="font-mono">{a.nom}</span> <Marque>{a.ecrit ? t({ en: "Writes", fr: "Écrit" }) : t({ en: "Reads", fr: "Lit" })}</Marque>
                                    <span className="block text-xs font-normal text-muted-foreground">{a.description}</span>
                                </span>
                            }
                        >
                            <Button variant="outline" size="sm" onClick={() => void creerUnOutil(a.nom)}>
                                {t({ en: "Create a tool", fr: "Créer un outil" })}
                            </Button>
                        </LigneChamp>
                    ))}
                </Champs>
            )}
            {onglet === "apropos" && (
                <Champs>
                    <LigneChamp libelle={t({ en: "Software key", fr: "Clé du logiciel" })}>
                        <span className="font-mono text-sm">{connecteur.integration}</span>
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Actions", fr: "Actions" })}>
                        <span className="text-sm tabular-nums">{connecteur.actions.length}</span>
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
        </FenetreOnglets>
    );
}
