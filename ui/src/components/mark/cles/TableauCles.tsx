"use client";

/**
 * [.mark] V2b (E51) : le tableau des clés de « Modèles et clés », comme la maquette : tableau nu « Clé · Sert à »,
 * « Ajouter une clé » en fenêtre, un clic sur une ligne ouvre la clé (où elle sert, et la supprimer).
 *
 * Les usages de TOUTES les clés viennent d'une seule lecture (`/cles/usages`), jamais une lecture par clé. La valeur
 * d'une clé n'est jamais lue ni affichée ; une suppression demande confirmation et dit où la clé servait.
 */
import { ChevronDown, ChevronRight, ExternalLink, KeyRound, MoreHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { supprimerUneCleApiV1ClesUuidDelete, usagesDeToutesLesClesApiV1ClesUsagesGet } from "@/client";
import { getWorkflowsSummaryApiV1WorkflowSummaryGet } from "@/client/sdk.gen";
import type { Cle, Usage } from "@/client/types.gen";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { Initiales } from "@/components/mark/integrations/OngletLogiciels";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Info } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { formatDate } from "@/lib/dateTime";

import { DESCRIPTION_BIBLIOTHEQUE, FormulaireAjoutCle, nomDu } from "./FenetreCles";

const estAgent = (u: Usage) => u.ou === "agent" || u.ou === "modeles_agent";

/** « Utilisée par » en compte : « 3 agents », « 2 outils », puis les autres endroits en quelques mots. Vide = « Aucun ». */
export function resumeDesUsages(usages: Usage[]): Texte | null {
    if (usages.length === 0) return null;
    const agents = new Set(usages.filter(estAgent).map((u) => u.nom ?? "")).size;
    const outils = new Set(usages.filter((u) => u.ou === "outil").map((u) => u.nom ?? "")).size;
    const autres = [...new Set(usages.filter((u) => !estAgent(u) && u.ou !== "outil").map((u) => texteUsageCourt(u)))];
    const morceaux: Texte[] = [];
    if (agents) morceaux.push({ en: `${agents} agent${agents > 1 ? "s" : ""}`, fr: `${agents} agent${agents > 1 ? "s" : ""}` });
    if (outils) morceaux.push({ en: `${outils} tool${outils > 1 ? "s" : ""}`, fr: `${outils} outil${outils > 1 ? "s" : ""}` });
    morceaux.push(...autres);
    return { en: morceaux.map((m) => m.en).join(" · "), fr: morceaux.map((m) => m.fr).join(" · ") };
}

/** Où une clé sert, en quelques mots (le tableau est court ; la fenêtre de la clé dit le détail). */
export function texteUsageCourt(u: Usage): Texte {
    switch (u.ou) {
        case "reglages_modele":
            return { en: "Simulated caller", fr: "Appelant simulé" };
        case "reglages_voix":
            return { en: "Simulated caller voice", fr: "Voix de l'appelant simulé" };
        case "outil":
            return { en: `Tool « ${u.nom ?? ""} »`, fr: `Outil « ${u.nom ?? ""} »` };
        case "agent":
        case "modeles_agent":
            return { en: `Agent « ${u.nom ?? ""} »`, fr: `Agent « ${u.nom ?? ""} »` };
        case "modeles_organisation":
            return { en: "Models of the organization", fr: "Modèles de l'organisation" };
        case "apres_appel":
            return { en: "After the call", fr: "Après l'appel" };
    }
}

const T = {
    titre: { en: "Keys", fr: "Clés" },
    ajouter: { en: "Add a key", fr: "Ajouter une clé" },
    cle: { en: "Key", fr: "Clé" },
    sert: { en: "Used by", fr: "Utilisée par" },
    nulle: { en: "None", fr: "Aucun" },
    creee: { en: "Created", fr: "Créée le" },
    sansNom: { en: "Unnamed", fr: "Sans nom" },
    menu: { en: "Key actions", fr: "Actions de la clé" },
    ouvrir: { en: "Open", fr: "Ouvrir" },
    fournisseur: { en: "Provider", fr: "Fournisseur" },
    adresse: { en: "Address", fr: "Adresse" },
    valeur: { en: "Value", fr: "Valeur" },
    valeurDite: { en: "Saved, never shown", fr: "Enregistrée, jamais affichée" },
    agents: { en: "Agents", fr: "Agents" },
    autresUsages: { en: "Elsewhere", fr: "Ailleurs" },
    replier: { en: "Collapse", fr: "Replier" },
    deplier: { en: "Expand", fr: "Déplier" },
    fermer: { en: "Close", fr: "Fermer" },
    vide: { en: "No key yet", fr: "Aucune clé pour l'instant" },
    supprimer: { en: "Delete the key", fr: "Supprimer la clé" },
    confirmer: { en: "Delete", fr: "Supprimer" },
    garder: { en: "Keep it", fr: "La garder" },
} satisfies Record<string, Texte>;

/** Les usages (clé -> endroits) ; `null` tant qu'ils ne sont pas lus. Une lecture manquée laisse `{}` : la colonne dit « nulle part » seulement si la lecture a réussi. */
function useUsages(rechargerAvec: unknown) {
    const [usages, setUsages] = useState<Record<string, Usage[]> | null>(null);
    useEffect(() => {
        // Seulement une fois les clés lues : c'est la preuve que la session est prête (le client d'API n'envoie rien avant).
        if (rechargerAvec === null) return;
        let annule = false;
        void usagesDeToutesLesClesApiV1ClesUsagesGet().then((reponse) => {
            if (!annule) setUsages(reponse.error ? null : ((reponse.data as Record<string, Usage[]> | undefined) ?? {}));
        });
        return () => {
            annule = true;
        };
    }, [rechargerAvec]);
    return usages;
}

export function TableauCles({
    cles,
    erreur,
    recharger,
    onChange,
}: {
    /** Lues UNE fois par la page (les cartes de modèles nomment leur clé avec la même lecture). */
    cles: Cle[] | null;
    erreur: string | null;
    recharger: () => Promise<void>;
    onChange?: () => void;
}) {
    const { t, langue } = useLangue();
    const usages = useUsages(cles);
    const [ajout, setAjout] = useState(false);
    const [ouverte, setOuverte] = useState<{ cle: Cle; supprimer: boolean } | null>(null);

    const apresChangement = useCallback(async () => {
        await recharger();
        onChange?.();
    }, [recharger, onChange]);

    return (
        <div data-testid="page-cles" className="space-y-1">
            <TitreTableau
                titre={t(T.titre)}
                info={<Info>{t(DESCRIPTION_BIBLIOTHEQUE)}</Info>}
                action={
                    <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setAjout(true)}>
                        + {t(T.ajouter)}
                    </Button>
                }
            />
            {erreur ? (
                <EtatVide cas="erreur" compact reessayer={() => void recharger()} />
            ) : cles === null ? (
                <EtatVide cas="chargement" lignes={3} />
            ) : cles.length === 0 ? (
                <EtatVide cas="premier" compact icone={KeyRound} titre={t(T.vide)} />
            ) : (
                <Tableau colonnes={[{ titre: t(T.cle) }, { titre: t(T.sert), secondaire: 2 }, { titre: t(T.creee), secondaire: 1 }, { titre: <span className="sr-only">{t(T.menu)}</span>, droite: true }]}>
                    {cles.map((c) => {
                        const ici = usages?.[c.uuid];
                        const dit = ici === undefined ? "" : t(resumeDesUsages(ici) ?? T.nulle);
                        return (
                            <Ligne key={c.uuid} onClick={() => setOuverte({ cle: c, supprimer: false })}>
                                <td className="py-3" data-cle-ligne={c.uuid}>
                                    <div className="flex items-center gap-3">
                                        <Initiales nom={nomDu(c.fournisseur)} integration={c.fournisseur} taille={32} />
                                        <span className="min-w-0">
                                            <span className="block truncate font-medium">{c.nom || t(T.sansNom)}</span>
                                            <span className="block truncate text-xs text-muted-foreground">{c.nom_fournisseur ?? nomDu(c.fournisseur)}</span>
                                        </span>
                                    </div>
                                </td>
                                <Cellule>{dit}</Cellule>
                                <Cellule className="whitespace-nowrap">{c.creee_le ? formatDate(c.creee_le, null, langue) : "–"}</Cellule>
                                <td className="pl-2 text-right" onClick={(e) => e.stopPropagation()}>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={`${t(T.menu)} : ${c.nom || t(T.sansNom)}`}>
                                                <MoreHorizontal className="size-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem className="cursor-pointer" onClick={() => setOuverte({ cle: c, supprimer: false })}>
                                                <ExternalLink className="mr-2 size-4" /> {t(T.ouvrir)}
                                            </DropdownMenuItem>
                                            <DropdownMenuItem className="cursor-pointer text-destructive focus:text-destructive" onClick={() => setOuverte({ cle: c, supprimer: true })}>
                                                <Trash2 className="mr-2 size-4" /> {t(T.supprimer)}
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </td>
                            </Ligne>
                        );
                    })}
                </Tableau>
            )}
            <FenetreChamps
                ouverte={ajout}
                fermer={() => setAjout(false)}
                titre={t(T.ajouter)}
                info={t(DESCRIPTION_BIBLIOTHEQUE)}
                sections={[]}
                lecture
                valider={t(T.fermer)}
                etroite
                corps={<FormulaireAjoutCle sansCadre onAjoutee={async () => {
                    setAjout(false);
                    await apresChangement();
                }} />}
            />
            {ouverte && (
                <PanneauDeLaCle
                    key={ouverte.cle.uuid}
                    cle={ouverte.cle}
                    usages={usages?.[ouverte.cle.uuid] ?? null}
                    confirmeDepart={ouverte.supprimer}
                    fermer={() => setOuverte(null)}
                    apresSuppression={apresChangement}
                />
            )}
        </div>
    );
}

/** Les agents de l'espace (id, nom) : une seule lecture à l'ouverture d'une clé, pour que chaque agent cité soit un lien. */
function useAgentsParNom(actif: boolean): Map<string, number | null> {
    const [agents, setAgents] = useState<Map<string, number | null>>(new Map());
    useEffect(() => {
        if (!actif) return;
        let annule = false;
        void (async () => {
            try {
                const r = await getWorkflowsSummaryApiV1WorkflowSummaryGet();
                if (annule || r.error || !r.data) return;
                const m = new Map<string, number | null>();
                // Deux agents du même nom : aucun lien (on ne devine pas lequel).
                for (const w of r.data) m.set(w.name, m.has(w.name) ? null : w.id);
                setAgents(m);
            } catch {
                /* les noms restent en texte simple */
            }
        })();
        return () => {
            annule = true;
        };
    }, [actif]);
    return agents;
}

/** Le panneau de droite d'une clé : fournisseur, adresse, création, valeur (jamais lue), où elle sert, suppression. */
function PanneauDeLaCle({
    cle,
    usages,
    confirmeDepart,
    fermer,
    apresSuppression,
}: {
    cle: Cle;
    usages: Usage[] | null;
    confirmeDepart: boolean;
    fermer: () => void;
    apresSuppression: () => Promise<void>;
}) {
    const { t, langue } = useLangue();
    const [confirme, setConfirme] = useState(confirmeDepart);
    const [enCours, setEnCours] = useState(false);
    const [repli, setRepli] = useState(true);
    const agentsParNom = useAgentsParNom(true);

    const supprimer = async () => {
        setEnCours(true);
        // suppression-confirmee : confirmation en place (`confirme`) avant `supprimer`.
        const reponse = await supprimerUneCleApiV1ClesUuidDelete({ path: { uuid: cle.uuid } });
        setEnCours(false);
        if (reponse.error) {
            notifier.echec({ fr: "La clé n'a pas été supprimée. Réessayez.", en: "The key was not deleted. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Clé supprimée.", en: "Key deleted." });
        fermer();
        await apresSuppression();
    };

    const noms = usages ? [...new Set(usages.filter(estAgent).map((u) => u.nom ?? ""))].filter(Boolean) : [];
    const autres = usages ? [...new Set(usages.filter((u) => !estAgent(u)).map((u) => t(texteUsageCourt(u))))] : [];
    const champs = [
        { id: "fournisseur", l: t(T.fournisseur), v: cle.nom_fournisseur ? `${nomDu(cle.fournisseur)} · ${cle.nom_fournisseur}` : nomDu(cle.fournisseur) },
        ...(cle.adresse ? [{ id: "adresse", l: t(T.adresse), v: cle.adresse }] : []),
        { id: "creee", l: t(T.creee), v: cle.creee_le ? formatDate(cle.creee_le, null, langue) : "–" },
        { id: "valeur", l: t(T.valeur), v: t(T.valeurDite) },
    ];

    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={cle.nom || t(T.sansNom)}
            sections={[]}
            lecture
            valider={t(T.fermer)}
            etroite
            corps={
                <>
                    <dl className="divide-y" data-fiche-cle>
                        {champs.map((c) => (
                            <div key={c.id} className="space-y-1 py-3.5 first:pt-0" data-champ-cle={c.id}>
                                <dt className="text-sm font-medium">{c.l}</dt>
                                <dd className="text-sm">{c.v}</dd>
                            </div>
                        ))}
                    </dl>
                    <section className="space-y-3" data-utilisee-par>
                        <p className="text-sm font-semibold">{t(T.sert)}</p>
                        {usages === null ? (
                            <EtatVide cas="chargement" />
                        ) : usages.length === 0 ? (
                            <p className="text-sm text-muted-foreground">{t(T.nulle)}</p>
                        ) : (
                            <div className="space-y-2 text-sm">
                                {noms.length > 0 && (
                                    <div>
                                        <button
                                            type="button"
                                            aria-expanded={!repli}
                                            aria-label={`${t(repli ? T.deplier : T.replier)} : ${t(T.agents)}`}
                                            data-usage-agents
                                            onClick={() => setRepli((r) => !r)}
                                            className="flex cursor-pointer items-center gap-1.5 hover:font-medium"
                                        >
                                            {repli ? <ChevronRight className="size-4 text-muted-foreground" aria-hidden /> : <ChevronDown className="size-4 text-muted-foreground" aria-hidden />}
                                            {t(T.agents)}
                                            <span className="text-muted-foreground">({noms.length})</span>
                                        </button>
                                        {!repli && (
                                            <ul className="mt-1 divide-y pl-6">
                                                {noms.map((n) => {
                                                    const id = agentsParNom.get(n);
                                                    return (
                                                        <li key={n} className="py-1.5">
                                                            {id ? (
                                                                <Link href={adresseOnglet(id, "parcours")} className="hover:font-medium" data-lien-agent={id}>
                                                                    {n}
                                                                </Link>
                                                            ) : (
                                                                n
                                                            )}
                                                        </li>
                                                    );
                                                })}
                                            </ul>
                                        )}
                                    </div>
                                )}
                                {autres.length > 0 && (
                                    <ul className="divide-y">
                                        {autres.map((a) => (
                                            <li key={a} className="py-1.5">
                                                {a}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}
                    </section>
                </>
            }
            pied={
                confirme ? (
                    <span className="flex items-center gap-2 text-sm">
                        <span>
                            {t({
                                en: "These settings will say « key deleted » until another is chosen.",
                                fr: "Les réglages qui l'utilisent diront « clé supprimée » jusqu'au choix d'une autre.",
                            })}
                        </span>
                        <Button size="sm" variant="outline" onClick={() => setConfirme(false)}>
                            {t(T.garder)}
                        </Button>
                        <Button size="sm" variant="destructive" disabled={enCours} onClick={() => void supprimer()}>
                            {t(T.confirmer)}
                        </Button>
                    </span>
                ) : (
                    <Button variant="ghost" className="cursor-pointer text-(--marque-danger-texte)" onClick={() => setConfirme(true)}>
                        {t(T.supprimer)}
                    </Button>
                )
            }
        />
    );
}
