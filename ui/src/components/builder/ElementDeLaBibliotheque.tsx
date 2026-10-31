"use client";

/**
 * [.mark] builder-agent-vocal (lot 2): one element of the library, with its versions and the human gestures
 * (new version, back to a version, move to Recipe with the bench that proves it, reject with the reason).
 *
 * The server decides who may write (members of the .mark organization): a refusal is shown as it comes, nothing is
 * hidden by guesswork. The builder itself never makes these gestures.
 */
import { useState } from "react";

import {
    ajouterUneVersionApiV1BuilderBibliothequeFamilleSlugVersionsPost,
    changerLeStatutApiV1BuilderBibliothequeFamilleSlugStatutPost,
    revenirEnArriereApiV1BuilderBibliothequeFamilleSlugRetourPost,
} from "@/client";
import type { Element as ElementBibliotheque } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { dateCourte, type StatutDeLaBibliotheque,STATUTS } from "./libelles";
import { AgentsDeLaRecette } from "./tests/AgentsDeLaRecette";

interface Props {
    element: ElementBibliotheque;
    utilisePar: number;
    onChange: (element: ElementBibliotheque) => void;
}

const CHAMP = "w-full rounded-md border bg-background px-2 py-1.5 text-sm";

export function ElementDeLaBibliotheque({ element, utilisePar, onChange }: Props) {
    const { t } = useLangue();
    const [nouveau, setNouveau] = useState<string | null>(null);
    const [notes, setNotes] = useState("");
    const [banc, setBanc] = useState("");
    const [raison, setRaison] = useState("");
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

    const marquer = async (cible: "recette" | "rejete") => {
        const reponse = await changerLeStatutApiV1BuilderBibliothequeFamilleSlugStatutPost({
            path: chemin,
            body:
                cible === "recette"
                    ? { version: courante.numero, statut: "recette", banc: { description: banc.trim() } }
                    : { version: courante.numero, statut: "rejete", raison: raison.trim() },
        });
        if (apres(reponse, "The status was not saved")) {
            setBanc("");
            setRaison("");
        }
    };

    const revenir = async (numero: number) => {
        apres(
            await revenirEnArriereApiV1BuilderBibliothequeFamilleSlugRetourPost({ path: chemin, body: { version: numero } }),
            "The rollback failed",
        );
    };

    return (
        <section className="space-y-4 rounded border p-4" data-testid="element-detail">
            <header className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{element.titre}</h2>
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUTS[statut].classe}`} data-testid="statut-courant">
                        {t(STATUTS[statut].texte)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                        {element.famille}/{element.slug} · v{courante.numero}
                    </span>
                </div>
                <p className="text-sm text-muted-foreground" data-testid="utilisee-par">
                    {t({ en: `Used by ${utilisePar} agent(s)`, fr: `Utilisée par ${utilisePar} agent(s)` })}
                </p>
                {statut === "recette" && <AgentsDeLaRecette famille={element.famille} slug={element.slug} />}
                {statut === "candidat" && (
                    <p className="text-sm text-(--signal-warn)" data-testid="avertissement-candidat">
                        {t({
                            en: "Candidate: the builder may use it but must say it is not proven. An agent that uses it carries the mention.",
                            fr: "Candidat : le builder peut l'utiliser mais doit dire qu'il n'est pas prouvé. Un agent qui l'utilise porte la mention.",
                        })}
                    </p>
                )}
                {courante.banc && (
                    <p className="text-sm" data-testid="banc-courant">
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
                        {t({ en: "Imported from", fr: "Importé depuis" })} {courante.origine.source} · {t({ en: "licence", fr: "licence" })}{" "}
                        {courante.origine.licence} · {courante.origine.date}
                    </p>
                )}
            </header>

            <pre className="max-h-64 overflow-auto rounded bg-muted p-3 text-xs" data-testid="contenu-courant">
                {JSON.stringify(courante.contenu, null, 2)}
            </pre>

            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}

            <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                    <h3 className="text-sm font-semibold">{t({ en: "Move to Recipe", fr: "Passer en Recette" })}</h3>
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "The bench that proves it", fr: "Le banc qui la prouve" })}</span>
                        <input className={CHAMP} value={banc} onChange={(e) => setBanc(e.target.value)} placeholder={t({ en: "e.g. 3 x 3 green on the 13 scenarios", fr: "ex. 3 x 3 verts sur les 13 scénarios" })} />
                    </label>
                    <Button size="sm" disabled={!banc.trim() || statut === "recette"} onClick={() => void marquer("recette")}>
                        {t({ en: "Promote to Recipe", fr: "Promouvoir en Recette" })}
                    </Button>
                </div>
                <div className="space-y-2">
                    <h3 className="text-sm font-semibold">{t({ en: "Reject", fr: "Rejeter" })}</h3>
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "The reason, kept with it", fr: "La raison, gardée avec lui" })}</span>
                        <input className={CHAMP} value={raison} onChange={(e) => setRaison(e.target.value)} />
                    </label>
                    <Button size="sm" variant="outline" disabled={!raison.trim() || statut === "rejete"} onClick={() => void marquer("rejete")}>
                        {t({ en: "Reject this version", fr: "Rejeter cette version" })}
                    </Button>
                </div>
            </div>

            <div className="space-y-2">
                <h3 className="text-sm font-semibold">{t({ en: "Versions", fr: "Versions" })}</h3>
                <ul className="space-y-1">
                    {[...element.versions].reverse().map((v) => (
                        <li key={v.numero} className="flex flex-wrap items-center gap-2 rounded border p-2 text-sm" data-testid={`version-${v.numero}`}>
                            <span className="font-mono text-xs">v{v.numero}</span>
                            <span className={`rounded px-1.5 py-0.5 text-xs ${STATUTS[(v.statut ?? "candidat") as StatutDeLaBibliotheque].classe}`}>
                                {t(STATUTS[(v.statut ?? "candidat") as StatutDeLaBibliotheque].texte)}
                            </span>
                            <span>{v.auteur}</span>
                            <span className="text-xs text-muted-foreground">{dateCourte(v.date)}</span>
                            {v.notes && <span className="text-xs italic">{v.notes}</span>}
                            {v.banc && <span className="text-xs">({v.banc.description})</span>}
                            {v.numero === element.version_courante ? (
                                <span className="ml-auto text-xs text-muted-foreground">{t({ en: "current", fr: "courante" })}</span>
                            ) : (
                                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => void revenir(v.numero)}>
                                    {t({ en: "Go back to this version", fr: "Revenir à cette version" })}
                                </Button>
                            )}
                        </li>
                    ))}
                </ul>
            </div>

            {nouveau === null ? (
                <Button size="sm" variant="outline" onClick={() => setNouveau(JSON.stringify(courante.contenu, null, 2))}>
                    {t({ en: "New version", fr: "Nouvelle version" })}
                </Button>
            ) : (
                <div className="space-y-2">
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "Content of the new version (JSON)", fr: "Contenu de la nouvelle version (JSON)" })}</span>
                        <textarea className={`${CHAMP} h-40 font-mono text-xs`} value={nouveau} onChange={(e) => setNouveau(e.target.value)} />
                    </label>
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "Notes", fr: "Notes" })}</span>
                        <input className={CHAMP} value={notes} onChange={(e) => setNotes(e.target.value)} />
                    </label>
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: "A new version is always a Candidate: it is proven on a bench before it becomes a Recipe.",
                            fr: "Une nouvelle version est toujours Candidate : elle se prouve au banc avant de devenir Recette.",
                        })}
                    </p>
                    <div className="flex gap-2">
                        <Button size="sm" onClick={() => void enregistrerUneVersion()}>
                            {t({ en: "Save the version", fr: "Enregistrer la version" })}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setNouveau(null)}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                    </div>
                </div>
            )}
        </section>
    );
}
