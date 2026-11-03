"use client";

/**
 * [.mark] K5 (fidélité à la maquette, E49) : la fiche d'un élément de la Bibliothèque dans une fenêtre, comme la maquette
 * (`FicheElement`) : Contenu, Versions (retour arrière), Utilisé par, Étiquettes ; au pied, les gestes humains : Rejeter,
 * Nouvelle version, Passer en Recette (un geste ouvre une ligne de saisie : le banc qui prouve, la raison du rejet).
 * Le serveur décide qui écrit (l'équipe de .mark) : un refus s'affiche tel quel. Le builder ne fait jamais ces gestes.
 */
import { Check, Pencil, RotateCcw } from "lucide-react";
import { useState } from "react";

import {
    ajouterUneVersionApiV1BuilderBibliothequeFamilleSlugVersionsPost,
    changerLeStatutApiV1BuilderBibliothequeFamilleSlugStatutPost,
    revenirEnArriereApiV1BuilderBibliothequeFamilleSlugRetourPost,
} from "@/client";
import type { Element as ElementBibliotheque, VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Carte, FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { dateCourte, type StatutDeLaBibliotheque, STATUTS } from "./libelles";
import { RangementDeLElement } from "./RangementDeLElement";
import { AgentsDeLaRecette } from "./tests/AgentsDeLaRecette";

const POINT = { recette: "publie", rejete: "panne", candidat: "brouillon" } as const;

interface Props {
    element: ElementBibliotheque;
    nomDeFamille: string;
    utilisePar: number;
    dossiers: string[];
    etiquettes: VueEtiquette[];
    fermer: () => void;
    /** L'élément a changé sur le serveur : la page relit sa liste. */
    onChange: (element: ElementBibliotheque) => void;
    /** Rangement (sous-dossier, étiquettes) : la page relit aussi ses étiquettes et ses dossiers. */
    onRangement: (element: ElementBibliotheque) => void;
}

export function FenetreElement({ element, nomDeFamille, utilisePar, dossiers, etiquettes, fermer, onChange, onRangement }: Props) {
    const { t } = useLangue();
    const [geste, setGeste] = useState<"recette" | "rejet" | null>(null);
    const [texte, setTexte] = useState("");
    const [nouveau, setNouveau] = useState<string | null>(null);
    const [notes, setNotes] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);
    const courante = element.versions.find((v) => v.numero === element.version_courante) ?? element.versions[element.versions.length - 1];
    const statut = (courante.statut ?? "candidat") as StatutDeLaBibliotheque;
    const chemin = { famille: element.famille, slug: element.slug };

    const apres = (reponse: { data?: ElementBibliotheque; error?: unknown }, secours: string) => {
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, secours));
            return false;
        }
        setErreur(null);
        onChange(reponse.data);
        return true;
    };

    const enregistrerUneVersion = async () => {
        let contenu: unknown;
        try {
            contenu = JSON.parse(nouveau ?? "");
        } catch {
            setErreur(t({ en: "The content is not valid JSON.", fr: "Le contenu n'est pas du JSON valide." }));
            return;
        }
        if (typeof contenu !== "object" || contenu === null || Array.isArray(contenu)) {
            setErreur(t({ en: "The content is a JSON object.", fr: "Le contenu est un objet JSON." }));
            return;
        }
        const reponse = await ajouterUneVersionApiV1BuilderBibliothequeFamilleSlugVersionsPost({
            path: chemin,
            body: { contenu: contenu as Record<string, unknown>, notes },
        });
        if (apres(reponse, "The version was not saved")) {
            setNouveau(null);
            setNotes("");
        }
    };

    const marquer = async () => {
        if (!geste) return;
        const reponse = await changerLeStatutApiV1BuilderBibliothequeFamilleSlugStatutPost({
            path: chemin,
            body:
                geste === "recette"
                    ? { version: courante.numero, statut: "recette", banc: { description: texte.trim() } }
                    : { version: courante.numero, statut: "rejete", raison: texte.trim() },
        });
        if (apres(reponse, "The status was not saved")) {
            setTexte("");
            setGeste(null);
        }
    };

    const revenir = async (numero: number) => {
        apres(await revenirEnArriereApiV1BuilderBibliothequeFamilleSlugRetourPost({ path: chemin, body: { version: numero } }), "The rollback failed");
    };

    const pied = nouveau !== null ? (
        <>
            <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                aria-label={t({ en: "Notes", fr: "Notes" })}
                placeholder={t({ en: "Notes of the version", fr: "Notes de version" })}
                className="flex-1"
            />
            <Button variant="outline" onClick={() => setNouveau(null)}>
                {t({ en: "Cancel", fr: "Annuler" })}
            </Button>
            <Button onClick={() => void enregistrerUneVersion()}>{t({ en: "Save the version", fr: "Enregistrer la version" })}</Button>
        </>
    ) : geste ? (
        <>
            <Input
                autoFocus
                value={texte}
                onChange={(e) => setTexte(e.target.value)}
                aria-label={geste === "recette" ? t({ en: "The bench that proves it", fr: "Le banc qui la prouve" }) : t({ en: "The reason, kept with it", fr: "La raison, gardée avec lui" })}
                placeholder={
                    geste === "recette"
                        ? t({ en: "The bench that proves it (e.g. 274 on the headset, 30/10)", fr: "Le banc qui le prouve (ex. 274 au casque, 30/10)" })
                        : t({ en: "The reason of the rejection", fr: "La raison du rejet" })
                }
                className="flex-1"
            />
            <Button
                variant="outline"
                onClick={() => {
                    setGeste(null);
                    setTexte("");
                }}
            >
                {t({ en: "Cancel", fr: "Annuler" })}
            </Button>
            <Button
                disabled={!texte.trim()}
                className={geste === "rejet" ? "bg-(--pastille-urgente) text-white hover:bg-(--pastille-urgente)/90" : ""}
                onClick={() => void marquer()}
            >
                {geste === "recette" ? t({ en: "Promote to Recipe", fr: "Passer en Recette" }) : t({ en: "Reject this version", fr: "Rejeter cette version" })}
            </Button>
        </>
    ) : (
        <>
            <Button variant="ghost" className="text-(--pastille-urgente) hover:text-(--pastille-urgente)" disabled={statut === "rejete"} onClick={() => setGeste("rejet")}>
                {t({ en: "Reject", fr: "Rejeter" })}
            </Button>
            <span className="flex-1" />
            <Button variant="outline" onClick={() => setNouveau(JSON.stringify(courante.contenu, null, 2))}>
                <Pencil className="size-4" /> {t({ en: "New version", fr: "Nouvelle version" })}
            </Button>
            <Button disabled={statut === "recette"} onClick={() => setGeste("recette")}>
                <Check className="size-4" /> {t({ en: "Promote to Recipe", fr: "Passer en Recette" })}
            </Button>
        </>
    );

    return (
        <FenetreLarge
            testid="element-detail"
            fermer={fermer}
            titre={element.titre}
            sous={
                <span className="flex flex-wrap items-center gap-2">
                    {nomDeFamille}
                    {element.dossier && ` › ${element.dossier}`} · v{courante.numero} ·{" "}
                    <span data-testid="statut-courant">
                        <PointEtat etat={POINT[statut]}>{t(STATUTS[statut].texte)}</PointEtat>
                    </span>
                </span>
            }
            pied={pied}
        >
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            <Carte titre={t({ en: "Content", fr: "Contenu" })}>
                {nouveau !== null ? (
                    <>
                        <Textarea
                            rows={12}
                            className="font-mono text-xs"
                            aria-label={t({ en: "Content of the new version (JSON)", fr: "Contenu de la nouvelle version (JSON)" })}
                            value={nouveau}
                            onChange={(e) => setNouveau(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                            {t({
                                en: "A new version is always a Candidate: it is proven on a bench before it becomes a Recipe.",
                                fr: "Une nouvelle version est toujours Candidate : elle se prouve au banc avant de devenir Recette.",
                            })}
                        </p>
                    </>
                ) : (
                    <div className="max-h-64 space-y-3 overflow-auto" data-testid="contenu-courant">
                        {Object.entries((courante.contenu ?? {}) as Record<string, unknown>).map(([cle, valeur]) => (
                            <div key={cle} className="space-y-1">
                                {cle !== "texte" && <p className="text-xs text-muted-foreground">{cle}</p>}
                                <p className="text-sm whitespace-pre-wrap">
                                    {typeof valeur === "string" ? valeur : Array.isArray(valeur) && valeur.every((v) => typeof v === "string") ? valeur.join(" · ") : JSON.stringify(valeur, null, 2)}
                                </p>
                            </div>
                        ))}
                    </div>
                )}
                {statut === "candidat" && (
                    <p className="sr-only" data-testid="avertissement-candidat">
                        {t({
                            en: "Candidate: the builder may use it but must say it is not proven. An agent that uses it carries the mention.",
                            fr: "Candidat : le builder peut l'utiliser mais doit dire qu'il n'est pas prouvé. Un agent qui l'utilise porte la mention.",
                        })}
                    </p>
                )}
                {courante.banc && (
                    <p className="text-sm text-muted-foreground" data-testid="banc-courant">
                        {t({ en: "Proven by", fr: "Prouvée par" })} : {courante.banc.description}
                    </p>
                )}
                {courante.raison_rejet && (
                    <p className="text-sm text-destructive" data-testid="raison-rejet">
                        {t({ en: "Rejected because", fr: "Rejeté car" })} : {courante.raison_rejet}
                    </p>
                )}
                {courante.origine && (
                    <p className="text-xs text-muted-foreground" data-testid="origine-courante">
                        {t({ en: "Imported from", fr: "Importé depuis" })} {courante.origine.source} · {t({ en: "licence", fr: "licence" })} {courante.origine.licence} ·{" "}
                        {courante.origine.date}
                    </p>
                )}
            </Carte>
            <Carte
                titre={t({ en: "Versions", fr: "Versions" })}
                info={t({
                    en: "A new version enters as a Candidate. Going back to a version makes a new one, a copy of that one.",
                    fr: "Une nouvelle version entre en Candidat. Revenir à une version en crée une nouvelle, copie de celle-là.",
                })}
            >
                <div className="divide-y">
                    {[...element.versions].reverse().map((v) => {
                        const s = (v.statut ?? "candidat") as StatutDeLaBibliotheque;
                        return (
                            <div key={v.numero} className="flex items-start gap-3 py-2.5 text-sm" data-testid={`version-${v.numero}`}>
                                <span className="w-8 font-medium">v{v.numero}</span>
                                <div className="min-w-0 flex-1">
                                    <p>{v.notes || <span className="text-muted-foreground">{t({ en: "No notes", fr: "Sans notes" })}</span>}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {v.auteur} · {dateCourte(v.date)}
                                        {v.banc && ` · ${t({ en: "bench", fr: "banc" })} : ${v.banc.description}`}
                                    </p>
                                </div>
                                <PointEtat etat={POINT[s]}>{t(STATUTS[s].texte)}</PointEtat>
                                {v.numero === element.version_courante ? (
                                    <span className="w-[86px] text-right text-xs text-muted-foreground">{t({ en: "current", fr: "actuelle" })}</span>
                                ) : (
                                    <Button variant="ghost" size="sm" onClick={() => void revenir(v.numero)}>
                                        <RotateCcw className="size-3.5" /> <span className="sr-only">{t({ en: "Go back to this version", fr: "Revenir à cette version" })}</span>
                                        <span aria-hidden>{t({ en: "Go back", fr: "Revenir" })}</span>
                                    </Button>
                                )}
                            </div>
                        );
                    })}
                </div>
            </Carte>
            <Carte
                titre={t({ en: "Used by", fr: "Utilisé par" })}
                info={t({
                    en: "The agents built or set with this element. A new Recipe is offered to them as an update, never imposed.",
                    fr: "Les agents construits ou réglés avec cet élément. Une nouvelle Recette leur est proposée en mise à jour, jamais imposée.",
                })}
            >
                <p className="text-sm" data-testid="utilisee-par">
                    {t({ en: `Used by ${utilisePar} agent(s)`, fr: `Utilisée par ${utilisePar} agent(s)` })}
                </p>
                {statut === "recette" && <AgentsDeLaRecette famille={element.famille} slug={element.slug} />}
            </Carte>
            <Carte
                titre={t({ en: "Labels", fr: "Étiquettes" })}
                info={t({
                    en: "A free mark that crosses the families (recipe, bench, model). A label made here serves the whole library.",
                    fr: "Un repère libre qui traverse les familles (recette, banc, modèle). Une étiquette créée ici sert à toute la bibliothèque.",
                })}
            >
                <RangementDeLElement key={`rangement-${element.famille}/${element.slug}`} element={element} dossiers={dossiers} etiquettes={etiquettes} onChange={onRangement} />
            </Carte>
        </FenetreLarge>
    );
}
