"use client";

/**
 * [.mark] builder-agent-vocal (lot 2) then builder partie 2, E1 (U7, E49): the « Library » page.
 *
 * Left, the column: « New family », the families by group, and the sub-folders of the chosen family. On the right, a search in
 * the whole library, the status and label filters, then the elements in a bare table, 25 per page (server side, E61). A click
 * on a row opens the element: where it sits (sub-folder, labels), its versions, the human gestures. Everyone reads; only members
 * of the .mark organization write (the server says no to the others).
 */
import { Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost,
    lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet,
    lireUnElementApiV1BuilderBibliothequeFamilleSlugGet,
    listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet,
    listerLesEtiquettesApiV1BuilderBibliothequeEtiquettesGet,
    listerLesFamillesApiV1BuilderBibliothequeFamillesGet,
    parcourirApiV1BuilderBibliothequeParcourirGet,
    supprimerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersDelete,
} from "@/client";
import type { Element as ElementBibliotheque, Resume, VueEtiquette, VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Etiquette } from "@/components/mark/studio/marques";
import { Paginee } from "@/components/mark/studio/pagination";
import { Tableau } from "@/components/mark/studio/tableau";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { ColonneDesFamilles } from "./ColonneDesFamilles";
import { DepotDeDocument } from "./DepotDeDocument";
import { ElementDeLaBibliotheque } from "./ElementDeLaBibliotheque";
import { FenetreFiche, FenetreNouvelleFamille } from "./FenetresDeFamille";
import { FormulaireImport } from "./FormulaireImport";
import { GestionDesEtiquettes } from "./GestionDesEtiquettes";
import { type StatutDeLaBibliotheque, STATUTS } from "./libelles";
import { PropositionsDeLaBibliotheque } from "./PropositionsDeLaBibliotheque";
import { RangementDeLElement } from "./RangementDeLElement";

type Onglet = "elements" | "propositions" | "ajouter";
const PAR_PAGE = 25;

export function PageBibliotheque() {
    const { t } = useLangue();
    const [onglet, setOnglet] = useState<Onglet>("elements");
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
    const [ficheDe, setFicheDe] = useState<string | null>(null);
    const [gestion, setGestion] = useState(false);

    const chargerLesFamilles = useCallback(async () => {
        const reponse = await listerLesFamillesApiV1BuilderBibliothequeFamillesGet();
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The families could not be read"));
            return;
        }
        setFamilles(reponse.data);
    }, []);

    const chargerLesEtiquettes = useCallback(async () => {
        const reponse = await listerLesEtiquettesApiV1BuilderBibliothequeEtiquettesGet();
        if (!reponse.error && reponse.data) setEtiquettes(reponse.data);
    }, []);

    const chargerLesDossiers = useCallback(async (f: string) => {
        if (!f) {
            setDossiers([]);
            return;
        }
        const reponse = await listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet({ path: { famille: f } });
        setDossiers(!reponse.error && reponse.data ? reponse.data : []);
    }, []);

    useEffect(() => {
        void chargerLesFamilles();
        void chargerLesEtiquettes();
    }, [chargerLesFamilles, chargerLesEtiquettes]);

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
        const reponse = await parcourirApiV1BuilderBibliothequeParcourirGet({
            query: {
                famille: famille || undefined,
                statut: statut || undefined,
                dossier: dossier || undefined,
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

    return (
        <div className="space-y-4" data-testid="page-bibliotheque">
            <div role="tablist" className="flex gap-2 border-b">
                {(
                    [
                        ["elements", { en: "Elements", fr: "Éléments" }],
                        ["propositions", { en: "Proposals", fr: "Propositions" }],
                        ["ajouter", { en: "Add", fr: "Ajouter" }],
                    ] as const
                ).map(([id, texte]) => (
                    <button
                        key={id}
                        role="tab"
                        aria-selected={onglet === id}
                        className={`cursor-pointer px-3 py-2 text-sm ${onglet === id ? "border-b-2 border-primary font-medium" : "text-muted-foreground hover:font-medium"}`}
                        onClick={() => setOnglet(id)}
                    >
                        {t(texte)}
                    </button>
                ))}
            </div>

            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}

            {onglet === "propositions" && <PropositionsDeLaBibliotheque onDecision={() => void chargerLaListe()} />}

            {onglet === "ajouter" && (
                <div className="space-y-8">
                    <FormulaireImport
                        familles={familles}
                        familleChoisie={famille}
                        onCree={(f, slug, garderLEcran) => {
                            void chargerLaListe();
                            void ouvrir(f, slug);
                            if (!garderLEcran) setOnglet("elements");
                        }}
                    />
                    <DepotDeDocument
                        familles={familles}
                        familleChoisie={famille}
                        onDepose={(f, slug) => {
                            void chargerLaListe();
                            void ouvrir(f, slug);
                        }}
                    />
                </div>
            )}

            {onglet === "elements" && (
                <div className="grid gap-6 md:grid-cols-[15rem_1fr]">
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
                        onFiche={setFicheDe}
                    />

                    <div className="min-w-0 space-y-4">
                        <div className="flex flex-wrap items-center gap-3">
                            <div className="relative min-w-64 flex-1">
                                <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                                <Input
                                    value={saisie}
                                    className="pl-8"
                                    aria-label={t({ en: "Search the whole library", fr: "Rechercher dans toute la bibliothèque" })}
                                    placeholder={t({ en: "Search the whole library", fr: "Rechercher dans toute la bibliothèque" })}
                                    onChange={(e) => setSaisie(e.target.value)}
                                />
                            </div>
                            <Liste
                                valeur={statut}
                                changer={(v) => {
                                    setStatut(v as StatutDeLaBibliotheque | "");
                                    setPage(0);
                                }}
                                vide={t({ en: "All statuses", fr: "Tous les statuts" })}
                                options={(Object.keys(STATUTS) as StatutDeLaBibliotheque[]).map((s) => ({ valeur: s, libelle: t(STATUTS[s].texte) }))}
                                className="w-44"
                            />
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="filtre-etiquettes">
                            <span className="text-muted-foreground">{t({ en: "Labels", fr: "Étiquettes" })}</span>
                            {etiquettes.map((e) => (
                                <button
                                    key={e.nom}
                                    type="button"
                                    aria-pressed={filtre.includes(e.nom)}
                                    className={`cursor-pointer rounded-full ${filtre.includes(e.nom) ? "font-semibold ring-1 ring-(--acc)" : "hover:font-medium"}`}
                                    onClick={() => basculerEtiquette(e.nom)}
                                >
                                    <Etiquette>{e.nom}</Etiquette>
                                </button>
                            ))}
                            <button type="button" className="cursor-pointer text-(--acc) hover:font-medium" onClick={() => setGestion(true)}>
                                {t({ en: "Manage labels…", fr: "Gérer les étiquettes…" })}
                            </button>
                        </div>

                        {elements !== null && elements.length === 0 && (
                            <p className="py-8 text-center text-sm text-muted-foreground" data-testid="bibliotheque-vide">
                                {t({ en: "Nothing in the library for this filter.", fr: "Rien dans la bibliothèque pour ce filtre." })}
                            </p>
                        )}
                        {elements !== null && elements.length > 0 && (
                            <Paginee total={total} page={page} changerPage={setPage}>
                                <Tableau
                                    colonnes={[
                                        { titre: t({ en: "Element", fr: "Élément" }) },
                                        { titre: t({ en: "Status", fr: "Statut" }) },
                                        { titre: t({ en: "Family", fr: "Famille" }) },
                                        { titre: t({ en: "Version", fr: "Version" }) },
                                        { titre: t({ en: "Labels", fr: "Étiquettes" }) },
                                        { titre: t({ en: "Used by", fr: "Utilisée par" }), droite: true },
                                    ]}
                                >
                                    {elements.map((e) => {
                                        const ouvert = choisi?.famille === e.famille && choisi.slug === e.slug;
                                        return (
                                            <tr
                                                key={`${e.famille}/${e.slug}`}
                                                data-testid={`element-${e.famille}-${e.slug}`}
                                                className={`cursor-pointer hover:bg-muted/40 hover:font-medium ${ouvert ? "bg-muted/40" : ""}`}
                                                onClick={() => void ouvrir(e.famille, e.slug)}
                                            >
                                                <td className="py-3">
                                                    <span className="font-medium">{e.titre}</span>
                                                    {e.dossier && <span className="block text-xs text-muted-foreground">{e.dossier}</span>}
                                                    {e.extrait && <span className="block text-xs text-muted-foreground">{e.extrait}</span>}
                                                    {e.banc && <span className="block text-xs text-muted-foreground">{e.banc.description}</span>}
                                                </td>
                                                <td className="pl-4">
                                                    <span className={`rounded px-2 py-0.5 text-xs ${STATUTS[e.statut as StatutDeLaBibliotheque].classe}`}>
                                                        {t(STATUTS[e.statut as StatutDeLaBibliotheque].texte)}
                                                    </span>
                                                </td>
                                                <td className="pl-4 text-muted-foreground">{nomDeFamille(e.famille)}</td>
                                                <td className="pl-4 text-muted-foreground">{`v${e.version_courante} · ${e.auteur}`}</td>
                                                <td className="pl-4 text-xs text-muted-foreground">{(e.etiquettes ?? []).join(", ")}</td>
                                                <td className="pl-4 text-right text-muted-foreground tabular-nums">
                                                    {t({ en: `Used by ${e.utilisee_par ?? 0} agent(s)`, fr: `Utilisée par ${e.utilisee_par ?? 0} agent(s)` })}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </Tableau>
                            </Paginee>
                        )}

                        {detail && choisi && (
                            <div className="space-y-4">
                                <RangementDeLElement
                                    key={`rangement-${detail.famille}/${detail.slug}`}
                                    element={detail}
                                    dossiers={detail.famille === famille ? dossiers : [...new Set([detail.dossier ?? "", ...dossiers].filter(Boolean))]}
                                    etiquettes={etiquettes}
                                    onChange={apresRangement}
                                />
                                <ElementDeLaBibliotheque
                                    key={`${detail.famille}/${detail.slug}`}
                                    element={detail}
                                    utilisePar={utilisePar}
                                    onChange={(nouveau) => {
                                        setDetail(nouveau);
                                        void chargerLaListe();
                                    }}
                                />
                            </div>
                        )}
                    </div>
                </div>
            )}

            <FenetreNouvelleFamille
                ouverte={nouvelleFamille}
                fermer={() => setNouvelleFamille(false)}
                apres={(slug) => {
                    void chargerLesFamilles();
                    choisirLaFamille(slug);
                }}
            />
            <FenetreFiche famille={familles.find((f) => f.slug === ficheDe) ?? null} fermer={() => setFicheDe(null)} apres={() => void chargerLesFamilles()} />
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
