"use client";

/**
 * [.mark] builder-agent-vocal (lot 2), builder partie 2 E1 (U7, E49), puis K5 (fidélité à la maquette) : la page « Bibliothèque ».
 *
 * À gauche, la colonne : « Nouvelle famille », les familles par groupe, les sous-dossiers de la famille choisie. À droite,
 * le nom de la famille (son « !», son crayon qui ouvre sa fiche), « Propositions » et « Nouvel élément » ; la recherche dans
 * toute la bibliothèque, les statuts en pastilles, le menu « Étiquettes » ; le tableau nu, 25 par page (côté serveur, E61).
 * Un clic sur une ligne ouvre la fiche de l'élément dans une fenêtre. Tout le monde lit ; seuls les membres de
 * l'organisation .mark écrivent (le serveur dit non aux autres).
 */
import { BookOpen, Pencil, Plus, Search, Tag } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost,
    creerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPost,
    lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet,
    lireUnElementApiV1BuilderBibliothequeFamilleSlugGet,
    listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet,
    listerLesEtiquettesApiV1BuilderBibliothequeEtiquettesGet,
    listerLesFamillesApiV1BuilderBibliothequeFamillesGet,
    listerLesPropositionsApiV1BuilderBibliothequePropositionsGet,
    parcourirApiV1BuilderBibliothequeParcourirGet,
    supprimerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersDelete,
} from "@/client";
import type { Element as ElementBibliotheque, Resume, VueEtiquette, VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Info, Pastille, PointEtat } from "@/components/mark/studio/marques";
import { Paginee } from "@/components/mark/studio/pagination";
import { Tableau } from "@/components/mark/studio/tableau";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { ColonneDesFamilles } from "./ColonneDesFamilles";
import { FenetreElement } from "./FenetreElement";
import { FenetreNouvelElement } from "./FenetreNouvelElement";
import { FenetreFiche, FenetreNouvelleFamille } from "./FenetresDeFamille";
import { GestionDesEtiquettes } from "./GestionDesEtiquettes";
import { type StatutDeLaBibliotheque, STATUTS } from "./libelles";
import { PropositionsDeLaBibliotheque } from "./PropositionsDeLaBibliotheque";

const PAR_PAGE = 25;
const POINT = { recette: "publie", rejete: "panne", candidat: "brouillon" } as const;

export function PageBibliotheque() {
    const { t } = useLangue();
    const [familles, setFamilles] = useState<VueFamille[]>([]);
    const [famille, setFamille] = useState("");
    const [dossier, setDossier] = useState<string | null>(null);
    const [dossiers, setDossiers] = useState<string[]>([]);
    const [statut, setStatut] = useState<StatutDeLaBibliotheque | "">("");
    const [saisie, setSaisie] = useState("");
    const [recherche, setRecherche] = useState("");
    const [etiquettes, setEtiquettes] = useState<VueEtiquette[]>([]);
    const [filtre, setFiltre] = useState<string[]>([]);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const [elements, setElements] = useState<Resume[] | null>(null);
    const [choisi, setChoisi] = useState<{ famille: string; slug: string } | null>(null);
    const [detail, setDetail] = useState<ElementBibliotheque | null>(null);
    const [utilisePar, setUtilisePar] = useState(0);
    const [erreur, setErreur] = useState<string | null>(null);
    const [nouvelleFamille, setNouvelleFamille] = useState(false);
    const [nouvelElement, setNouvelElement] = useState(false);
    const [ficheDe, setFicheDe] = useState<string | null>(null);
    const [gestion, setGestion] = useState(false);
    const [propositionsOuvertes, setPropositionsOuvertes] = useState(false);
    const [enAttente, setEnAttente] = useState(0);

    const chargerLesFamilles = useCallback(async () => {
        const reponse = await listerLesFamillesApiV1BuilderBibliothequeFamillesGet();
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The families could not be read"));
            return;
        }
        setFamilles(reponse.data);
        // Une famille est toujours choisie (la maquette n'a pas de « toutes les familles ») : la première, au début.
        setFamille((actuelle) => (actuelle && reponse.data.some((f) => f.slug === actuelle) ? actuelle : (reponse.data[0]?.slug ?? "")));
    }, []);

    const chargerLesEtiquettes = useCallback(async () => {
        const reponse = await listerLesEtiquettesApiV1BuilderBibliothequeEtiquettesGet();
        if (!reponse.error && reponse.data) setEtiquettes(reponse.data);
    }, []);

    const chargerLesPropositions = useCallback(async () => {
        const reponse = await listerLesPropositionsApiV1BuilderBibliothequePropositionsGet();
        if (!reponse.error && Array.isArray(reponse.data)) setEnAttente(reponse.data.filter((p) => p.etat === "en_attente").length);
    }, []);

    const chargerLesDossiers = useCallback(async (f: string) => {
        if (!f) {
            setDossiers([]);
            return;
        }
        const reponse = await listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet({ path: { famille: f } });
        setDossiers(!reponse.error && reponse.data ? reponse.data : []);
    }, []);

    // Les trois lectures de la page partent ensemble, jamais en chaîne.
    useEffect(() => {
        void chargerLesFamilles();
        void chargerLesEtiquettes();
        void chargerLesPropositions();
    }, [chargerLesFamilles, chargerLesEtiquettes, chargerLesPropositions]);

    useEffect(() => {
        void chargerLesDossiers(famille);
    }, [famille, chargerLesDossiers]);

    // La recherche part un instant après la dernière frappe.
    useEffect(() => {
        const minuteur = setTimeout(() => {
            setRecherche(saisie.trim());
            setPage(0);
        }, 250);
        return () => clearTimeout(minuteur);
    }, [saisie]);

    const chargerLaListe = useCallback(async () => {
        // Une recherche porte sur toute la bibliothèque ; sans elle, la famille choisie.
        const reponse = await parcourirApiV1BuilderBibliothequeParcourirGet({
            query: {
                famille: recherche ? undefined : famille || undefined,
                statut: statut || undefined,
                dossier: recherche ? undefined : dossier || undefined,
                etiquette: filtre.length ? filtre : undefined,
                q: recherche || undefined,
                limite: PAR_PAGE,
                decalage: page * PAR_PAGE,
            },
        });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The library could not be read"));
            return;
        }
        setErreur(null);
        setElements(reponse.data.elements);
        setTotal(reponse.data.total);
    }, [famille, statut, dossier, filtre, recherche, page]);

    useEffect(() => {
        void chargerLaListe();
    }, [chargerLaListe]);

    const ouvrir = useCallback(async (f: string, slug: string) => {
        setChoisi({ famille: f, slug });
        const [element, usage] = await Promise.all([
            lireUnElementApiV1BuilderBibliothequeFamilleSlugGet({ path: { famille: f, slug } }),
            lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet({ path: { famille: f, slug } }),
        ]);
        if (element.error || !element.data) {
            setErreur(detailFromError(element.error, "The element could not be read"));
            return;
        }
        setDetail(element.data);
        setUtilisePar((usage.data as { nombre?: number } | undefined)?.nombre ?? 0);
    }, []);

    const choisirLaFamille = (slug: string) => {
        setFamille(slug);
        setDossier(null);
        setSaisie("");
        setRecherche("");
        setPage(0);
    };
    const nomDeFamille = (slug: string) => familles.find((f) => f.slug === slug)?.libelle ?? slug;
    const basculerEtiquette = (nom: string) => {
        setFiltre((x) => (x.includes(nom) ? x.filter((n) => n !== nom) : [...x, nom]));
        setPage(0);
    };
    const apresRangement = (element: ElementBibliotheque) => {
        setDetail(element);
        void chargerLaListe();
        void chargerLesEtiquettes();
        void chargerLesDossiers(famille);
    };

    const aFiltrer = Boolean(recherche || statut || dossier || filtre.length);
    const familleCourante = familles.find((f) => f.slug === famille);

    return (
        <div className="space-y-6" data-testid="page-bibliotheque">
            <TitrePage
                titre={t({ en: "Library", fr: "Bibliothèque" })}
                info={t({
                    en: "What the builder draws from to build an agent: structures, prompts, sentences, templates, tests. A Candidate is not proven; a Recipe is proven on a bench and accepted by a person.",
                    fr: "Ce que le builder utilise pour construire un agent : structures, prompts, phrases, modèles, tests. Un Candidat n'est pas prouvé ; une Recette est prouvée au banc et acceptée par une personne.",
                })}
            />
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            <div className="grid gap-6 lg:grid-cols-[250px_1fr]">
                <ColonneDesFamilles
                    familles={familles}
                    famille={famille}
                    dossier={dossier}
                    dossiers={dossiers}
                    onFamille={choisirLaFamille}
                    onDossier={(d) => {
                        setDossier(d);
                        setPage(0);
                    }}
                    onNouvelleFamille={() => setNouvelleFamille(true)}
                    onNouveauDossier={async (chemin) => {
                        const reponse = await creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost({
                            path: { famille },
                            body: { chemin },
                        });
                        if (reponse.error) notifier.echec({ fr: "Dossier non créé. Réessayez.", en: "Folder not created. Try again." }, { erreur: reponse.error });
                        else void chargerLesDossiers(famille);
                    }}
                    onSupprimerDossier={async (chemin) => {
                        const reponse = await supprimerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersDelete({
                            path: { famille },
                            query: { chemin },
                        });
                        if (reponse.error) notifier.echec({ fr: "Dossier non retiré. Réessayez.", en: "Folder not removed. Try again." }, { erreur: reponse.error });
                        else {
                            if (dossier === chemin) setDossier(null);
                            void chargerLesDossiers(famille);
                        }
                    }}
                />

                <div className="min-w-0 space-y-4">
                    <div className="flex items-center gap-2">
                        <p className="font-medium">
                            {recherche ? t({ en: "The whole library", fr: "Toute la bibliothèque" }) : nomDeFamille(famille)}
                            {dossier && !recherche && <span className="text-muted-foreground"> › {dossier}</span>}
                        </p>
                        {!recherche && familleCourante && (
                            <>
                                <Info>{[familleCourante.fiche?.description, familleCourante.fiche?.quand].filter(Boolean).join(" ")}</Info>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 text-muted-foreground"
                                    title={t({ en: "Sheet of the family", fr: "Fiche de la famille" })}
                                    aria-label={t({ en: "Sheet of the family", fr: "Fiche de la famille" })}
                                    onClick={() => setFicheDe(famille)}
                                >
                                    <Pencil className="size-4" />
                                </Button>
                            </>
                        )}
                        <div className="ml-auto flex items-center gap-2">
                            <Button variant="outline" size="sm" onClick={() => setPropositionsOuvertes(true)}>
                                {t({ en: "Proposals", fr: "Propositions" })}
                                {enAttente > 0 && <Pastille n={enAttente} />}
                            </Button>
                            <Button size="sm" onClick={() => setNouvelElement(true)}>
                                <Plus className="size-4" /> {t({ en: "New element", fr: "Nouvel élément" })}
                            </Button>
                        </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="relative w-full max-w-72">
                            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                value={saisie}
                                className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
                                aria-label={t({ en: "Search the whole library", fr: "Rechercher dans toute la bibliothèque" })}
                                placeholder={t({ en: "Search the whole library", fr: "Rechercher dans toute la bibliothèque" })}
                                onChange={(e) => setSaisie(e.target.value)}
                            />
                        </div>
                        {(Object.keys(STATUTS) as StatutDeLaBibliotheque[]).map((s) => (
                            <Button
                                key={s}
                                variant="outline"
                                size="sm"
                                aria-pressed={statut === s}
                                onClick={() => {
                                    setStatut(statut === s ? "" : s);
                                    setPage(0);
                                }}
                                className={`rounded-full ${statut === s ? "border-foreground bg-foreground text-background hover:bg-foreground/90 hover:text-background" : ""}`}
                            >
                                {t(STATUTS[s].texte)}
                            </Button>
                        ))}
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className={`rounded-full ${filtre.length ? "border-foreground bg-foreground text-background hover:bg-foreground/90 hover:text-background" : ""}`}
                                >
                                    <Tag className="size-3.5" /> {t({ en: "Labels", fr: "Étiquettes" })}
                                    {filtre.length ? ` (${filtre.length})` : ""}
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56" data-testid="filtre-etiquettes">
                                {etiquettes.map((e) => (
                                    <DropdownMenuCheckboxItem key={e.nom} checked={filtre.includes(e.nom)} onCheckedChange={() => basculerEtiquette(e.nom)} onSelect={(ev) => ev.preventDefault()}>
                                        {e.nom}
                                    </DropdownMenuCheckboxItem>
                                ))}
                                {etiquettes.length > 0 && <DropdownMenuSeparator />}
                                <DropdownMenuItem onSelect={() => setGestion(true)}>
                                    <Pencil className="size-3.5" /> {t({ en: "Manage labels…", fr: "Gérer les étiquettes…" })}
                                </DropdownMenuItem>
                                <div className="p-1">
                                    <Input
                                        placeholder={t({ en: "New label", fr: "Nouvelle étiquette" })}
                                        aria-label={t({ en: "New label", fr: "Nouvelle étiquette" })}
                                        className="h-8 text-sm"
                                        onKeyDown={(e) => {
                                            e.stopPropagation();
                                            if (e.key !== "Enter") return;
                                            const champ = e.currentTarget;
                                            const nom = champ.value.trim();
                                            if (!nom) return;
                                            champ.value = "";
                                            void creerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPost({ body: { nom } }).then((r) => {
                                                if (r.error) notifier.echec({ fr: "Étiquette non créée. Réessayez.", en: "Label not created. Try again." }, { erreur: r.error });
                                                else void chargerLesEtiquettes();
                                            });
                                        }}
                                    />
                                </div>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>

                    {elements === null && !erreur && <EtatVide cas="chargement" />}
                    {elements !== null && elements.length === 0 && (
                        <div data-testid="bibliotheque-vide">
                            {aFiltrer ? (
                                <EtatVide
                                    cas="filtre"
                                    recherche={recherche || [dossier, statut && t(STATUTS[statut].texte), ...filtre].filter(Boolean).join(", ")}
                                    effacer={() => {
                                        setSaisie("");
                                        setRecherche("");
                                        setDossier(null);
                                        setStatut("");
                                        setFiltre([]);
                                        setPage(0);
                                    }}
                                />
                            ) : (
                                <EtatVide cas="premier" icone={BookOpen} titre={t({ en: "No element", fr: "Aucun élément" })} />
                            )}
                        </div>
                    )}
                    {elements !== null && elements.length > 0 && (
                        <Paginee total={total} page={page} changerPage={setPage}>
                            <Tableau
                                colonnes={[
                                    { titre: t({ en: "Element", fr: "Élément" }) },
                                    { titre: t({ en: "Status", fr: "Statut" }) },
                                    { titre: t({ en: "Version", fr: "Version" }) },
                                    { titre: t({ en: "Agents", fr: "Agents" }), droite: true },
                                ]}
                            >
                                {elements.map((e) => {
                                    const sous = [recherche ? nomDeFamille(e.famille) : null, e.dossier, ...(e.etiquettes ?? [])].filter(Boolean).join(" · ");
                                    const s = e.statut as StatutDeLaBibliotheque;
                                    return (
                                        <tr
                                            key={`${e.famille}/${e.slug}`}
                                            data-testid={`element-${e.famille}-${e.slug}`}
                                            className="cursor-pointer hover:bg-muted/40 hover:font-medium"
                                            onClick={() => void ouvrir(e.famille, e.slug)}
                                        >
                                            <td className="py-3">
                                                <span className="font-medium">{e.titre}</span>
                                                {sous && <span className="block text-xs text-muted-foreground">{sous}</span>}
                                                {e.extrait && <span className="block text-xs text-muted-foreground">{e.extrait}</span>}
                                                {e.banc && <span className="block text-xs text-muted-foreground">{e.banc.description}</span>}
                                            </td>
                                            <td className="pl-4">
                                                <PointEtat etat={POINT[s]}>{t(STATUTS[s].texte)}</PointEtat>
                                            </td>
                                            <td className="pl-4 text-muted-foreground">{`v${e.version_courante}`}</td>
                                            <td className="pl-4 text-right text-muted-foreground tabular-nums" data-testid="nb-agents">
                                                {e.utilisee_par ? e.utilisee_par : "–"}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </Tableau>
                        </Paginee>
                    )}
                </div>
            </div>

            {detail && choisi && (
                <FenetreElement
                    key={`${detail.famille}/${detail.slug}`}
                    element={detail}
                    nomDeFamille={nomDeFamille(detail.famille)}
                    utilisePar={utilisePar}
                    dossiers={detail.famille === famille ? dossiers : [...new Set([detail.dossier ?? "", ...dossiers].filter(Boolean))]}
                    etiquettes={etiquettes}
                    fermer={() => {
                        setDetail(null);
                        setChoisi(null);
                    }}
                    onChange={(nouveau) => {
                        setDetail(nouveau);
                        void chargerLaListe();
                    }}
                    onRangement={apresRangement}
                />
            )}
            {nouvelElement && (
                <FenetreNouvelElement
                    familles={familles}
                    famille={famille}
                    dossier={dossier}
                    etiquettes={etiquettes}
                    fermer={() => setNouvelElement(false)}
                    onRelire={() => {
                        void chargerLaListe();
                        void chargerLesEtiquettes();
                    }}
                    onCree={(f, slug) => {
                        setNouvelElement(false);
                        void chargerLaListe();
                        void chargerLesEtiquettes();
                        void chargerLesDossiers(famille);
                        void ouvrir(f, slug);
                    }}
                />
            )}
            {propositionsOuvertes && (
                <FenetreLarge
                    liste
                    testid="propositions-bibliotheque"
                    fermer={() => setPropositionsOuvertes(false)}
                    titre={t({ en: "Proposals", fr: "Propositions" })}
                    sous={t({ en: "What the builder offers: a person accepts or refuses.", fr: "Ce que le builder propose : une personne accepte ou refuse." })}
                    pied={
                        <>
                            <span className="flex-1" />
                            <Button onClick={() => setPropositionsOuvertes(false)}>{t({ en: "Close", fr: "Fermer" })}</Button>
                        </>
                    }
                >
                    <PropositionsDeLaBibliotheque
                        onDecision={() => {
                            void chargerLaListe();
                            void chargerLesPropositions();
                            void chargerLesFamilles();
                        }}
                    />
                </FenetreLarge>
            )}
            <FenetreNouvelleFamille
                ouverte={nouvelleFamille}
                fermer={() => setNouvelleFamille(false)}
                apres={(slug) => {
                    void chargerLesFamilles();
                    choisirLaFamille(slug);
                }}
            />
            <FenetreFiche key={ficheDe ?? "aucune"} famille={familles.find((f) => f.slug === ficheDe) ?? null} fermer={() => setFicheDe(null)} apres={() => void chargerLesFamilles()} />
            {gestion && (
                <GestionDesEtiquettes
                    etiquettes={etiquettes}
                    fermer={() => setGestion(false)}
                    apres={() => {
                        void chargerLesEtiquettes();
                        void chargerLaListe();
                        setFiltre((x) => x.filter((n) => etiquettes.some((e) => e.nom === n)));
                    }}
                />
            )}
        </div>
    );
}
