"use client";

/**
 * [.mark] K5 (fidélité à la maquette) : « Connaissances » : les documents que lisent les agents de l'organisation.
 *
 * Comme la maquette : le titre et son « ! » (les deux modes de lecture), « Déposer un document », le tableau nu (document,
 * lecture, état), une fenêtre « Déposer un document » (le fichier, le mode de lecture). Une ligne ouvre la fenêtre du
 * document : ce qu'on sait de lui, « Modifier le contenu » (texte et Markdown), « Supprimer » (annulable 5 s). Les
 * mêmes routes que l'écran d'amont `/files` (qu'on ne touche pas). Aucun document n'est lu d'une autre organisation.
 */
import { FileText, RefreshCw, Search, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import DocumentEditor, { isEditableDocument } from "@/app/files/DocumentEditor";
import ExternalProcessingNotice from "@/app/files/ExternalProcessingNotice";
import { deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete, listDocumentsApiV1KnowledgeBaseDocumentsGet } from "@/client/sdk.gen";
import type { DocumentResponseSchema } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { FenetreLibre } from "../studio/fenetre-libre";
import { Segmente } from "../studio/fenetre-onglets";
import { Info, PointEtat } from "../studio/marques";
import { Paginee } from "../studio/pagination";
import { PageStudio } from "../studio/shell-studio";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import { TitrePage } from "../studio/titre-page";
import { deposerUnDocument, type ModeDeLecture, verifierLeFichier } from "./deposer";

const occupe = (d: DocumentResponseSchema) => d.processing_status === "processing" || d.processing_status === "pending";
const taille = (octets: number) => (octets < 1024 ? `${octets} o` : octets < 1024 * 1024 ? `${Math.round(octets / 1024)} Ko` : `${(octets / 1024 / 1024).toFixed(1)} Mo`);

export function PageConnaissances() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [documents, setDocuments] = useState<DocumentResponseSchema[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [q, setQ] = useState("");
    const [depot, setDepot] = useState(false);
    const [ouvert, setOuvert] = useState<DocumentResponseSchema | null>(null);
    const [edite, setEdite] = useState<DocumentResponseSchema | null>(null);
    const [masques, setMasques] = useState<string[]>([]);
    const dejaLu = useRef(false);

    const relire = useCallback(async () => {
        try {
            const r = await listDocumentsApiV1KnowledgeBaseDocumentsGet({ query: { limit: 100, offset: 0 } });
            if (r.error || !r.data) throw new Error("documents");
            setDocuments(r.data.documents);
            setErreur(false);
        } catch {
            setErreur(true);
        }
    }, []);

    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [loading, user, relire]);

    // Un document en cours d'analyse se relit toutes les 5 secondes.
    useEffect(() => {
        if (!documents?.some(occupe)) return;
        const minuteur = setInterval(() => void relire(), 5000);
        return () => clearInterval(minuteur);
    }, [documents, relire]);

    const supprimer = (d: DocumentResponseSchema) => {
        setOuvert(null);
        setMasques((m) => [...m, d.document_uuid]);
        const remettre = () => setMasques((m) => m.filter((x) => x !== d.document_uuid));
        notifier.annulable(
            { fr: `Document « ${d.filename} » supprimé.`, en: `Document "${d.filename}" deleted.` },
            {
                restaurer: remettre,
                executer: async () => {
                    const r = await deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete({ path: { document_uuid: d.document_uuid } });
                    if (r.error) {
                        remettre();
                        notifier.echec({ fr: "Suppression impossible. Réessayez.", en: "Could not delete. Try again." }, { erreur: r.error });
                        return;
                    }
                    await relire();
                    remettre();
                },
            },
        );
    };

    const etat = (d: DocumentResponseSchema) => {
        if (d.has_live_content && occupe(d)) return <PointEtat etat="brouillon">{t({ en: "Updating", fr: "Mise à jour" })}</PointEtat>;
        if (d.has_live_content && d.processing_status === "failed") return <PointEtat etat="panne">{t({ en: "Update failed", fr: "Mise à jour échouée" })}</PointEtat>;
        if (d.processing_status === "completed") return <PointEtat etat="publie">{t({ en: "Ready", fr: "Prêt" })}</PointEtat>;
        if (occupe(d)) return <PointEtat etat="brouillon">{t({ en: "Being read", fr: "Lecture en cours" })}</PointEtat>;
        return <PointEtat etat="panne">{t({ en: "Failed", fr: "Échec" })}</PointEtat>;
    };
    const lecture = (d: DocumentResponseSchema) =>
        d.retrieval_mode === "full_document" ? t({ en: "Whole document", fr: "Document entier" }) : t({ en: "Search by excerpts", fr: "Recherche par extraits" });

    const liste = (documents ?? []).filter((d) => !masques.includes(d.document_uuid) && d.filename.toLowerCase().includes(q.toLowerCase()));

    return (
        <PageStudio>
            <div className="space-y-6">
                <TitrePage
                    titre={t({ en: "Knowledge", fr: "Connaissances" })}
                    info={t({
                        en: "Reading modes: the whole document, or a search by excerpts. The documents are shared by all the agents of the organization.",
                        fr: "Modes de lecture : document entier, ou recherche par extraits. Les documents sont partagés par tous les agents de l'organisation.",
                    })}
                    action={
                        <Button onClick={() => setDepot(true)}>
                            <Upload className="size-4" /> {t({ en: "Drop a document", fr: "Déposer un document" })}
                        </Button>
                    }
                />
                {documents && documents.length > 0 && (
                    <div className="flex items-center gap-2">
                        <div className="relative w-full max-w-72">
                            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                aria-label={t({ en: "Search a document", fr: "Rechercher un document" })}
                                placeholder={t({ en: "Search a document", fr: "Rechercher un document" })}
                                className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
                            />
                        </div>
                        <Button variant="ghost" size="icon" aria-label={t({ en: "Read again", fr: "Relire" })} onClick={() => void relire()}>
                            <RefreshCw className="size-4" />
                        </Button>
                    </div>
                )}
                {erreur && <EtatVide cas="erreur" reessayer={() => void relire()} />}
                {!erreur && documents === null && <EtatVide cas="chargement" />}
                {!erreur &&
                    documents !== null &&
                    liste.length === 0 &&
                    (documents.length === 0 ? (
                        <EtatVide cas="premier" icone={FileText} titre={t({ en: "No document", fr: "Aucun document" })} />
                    ) : (
                        <EtatVide cas="filtre" recherche={q} effacer={() => setQ("")} />
                    ))}
                {!erreur && liste.length > 0 && (
                    <Paginee liste={liste}>
                        {(page) => (
                            <Tableau
                                colonnes={[
                                    { titre: t({ en: "Document", fr: "Document" }) },
                                    { titre: t({ en: "Reading", fr: "Lecture" }) },
                                    { titre: t({ en: "State", fr: "État" }) },
                                    { titre: t({ en: "Added", fr: "Ajouté" }), droite: true },
                                ]}
                            >
                                {page.map((d) => (
                                    <Ligne key={d.document_uuid} onClick={() => setOuvert(d)}>
                                        <Cellule principale sous={taille(d.file_size_bytes)}>
                                            {d.filename}
                                        </Cellule>
                                        <Cellule>{lecture(d)}</Cellule>
                                        <Cellule>{etat(d)}</Cellule>
                                        <Cellule droite>{d.created_at.slice(0, 10)}</Cellule>
                                    </Ligne>
                                ))}
                            </Tableau>
                        )}
                    </Paginee>
                )}
            </div>
            {depot && <FenetreDepot fermer={() => setDepot(false)} apres={() => void relire()} />}
            {ouvert && (
                <FenetreDocument
                    document={ouvert}
                    etat={etat(ouvert)}
                    lecture={lecture(ouvert)}
                    fermer={() => setOuvert(null)}
                    modifier={() => {
                        setEdite(ouvert);
                        setOuvert(null);
                    }}
                    supprimer={() => supprimer(ouvert)}
                />
            )}
            <DocumentEditor
                doc={edite}
                onClose={() => setEdite(null)}
                onSaved={() => {
                    setEdite(null);
                    void relire();
                }}
            />
        </PageStudio>
    );
}

function FenetreDocument({
    document: d,
    etat,
    lecture,
    fermer,
    modifier,
    supprimer,
}: {
    document: DocumentResponseSchema;
    etat: React.ReactNode;
    lecture: string;
    fermer: () => void;
    modifier: () => void;
    supprimer: () => void;
}) {
    const { t } = useLangue();
    const ligne = (libelle: string, valeur: React.ReactNode) => (
        <div className="flex items-center gap-4 py-3 text-sm">
            <p className="flex-1 font-medium">{libelle}</p>
            <div className="text-muted-foreground">{valeur}</div>
        </div>
    );
    return (
        <FenetreLibre
            ouverte
            fermer={fermer}
            titre={<span className="truncate">{d.filename}</span>}
            corps={
                <div className="divide-y" data-testid="fenetre-document">
                    {ligne(t({ en: "Reading", fr: "Lecture" }), lecture)}
                    {ligne(t({ en: "State", fr: "État" }), etat)}
                    {ligne(t({ en: "Size", fr: "Taille" }), taille(d.file_size_bytes))}
                    {d.retrieval_mode !== "full_document" && d.processing_status === "completed" && ligne(t({ en: "Excerpts", fr: "Extraits" }), d.total_chunks)}
                    {ligne(t({ en: "Added", fr: "Ajouté" }), d.created_at.slice(0, 10))}
                    {d.has_live_content && occupe(d) && (
                        <p className="py-3 text-sm text-muted-foreground">
                            {t({ en: "Agents keep using the previous version until the update finishes.", fr: "Les agents gardent la version précédente jusqu'à la fin de la mise à jour." })}
                        </p>
                    )}
                    {d.processing_error && (
                        <p role="alert" className="py-3 text-sm text-destructive">
                            {t({ en: "The document could not be read.", fr: "Le document n'a pas pu être lu." })}
                            {d.has_live_content && ` ${t({ en: "Agents still use the previous version.", fr: "Les agents utilisent toujours la version précédente." })}`}
                        </p>
                    )}
                </div>
            }
            pied={
                <Button variant="ghost" className="text-(--pastille-urgente) hover:text-(--pastille-urgente)" onClick={supprimer}>
                    {t({ en: "Delete", fr: "Supprimer" })}
                </Button>
            }
            actions={
                <>
                    {isEditableDocument(d.filename) && (
                        <Button variant="outline" disabled={occupe(d)} onClick={modifier}>
                            {t({ en: "Edit the content", fr: "Modifier le contenu" })}
                        </Button>
                    )}
                    <Button onClick={fermer}>{t({ en: "Close", fr: "Fermer" })}</Button>
                </>
            }
        />
    );
}

function FenetreDepot({ fermer, apres }: { fermer: () => void; apres: () => void }) {
    const { t } = useLangue();
    const [fichier, setFichier] = useState<File | null>(null);
    const [mode, setMode] = useState<ModeDeLecture>("full_document");
    const [survol, setSurvol] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const entree = useRef<HTMLInputElement>(null);
    const entier = t({ en: "Whole document", fr: "Document entier" });
    const extraits = t({ en: "Search by excerpts", fr: "Recherche par extraits" });

    const choisir = (f: File | null | undefined) => {
        if (!f) return;
        const faute = verifierLeFichier(f);
        if (faute) {
            setErreur(
                faute === "type"
                    ? t({ en: "This file type is not accepted.", fr: "Ce type de fichier n'est pas pris en charge." })
                    : t({ en: "File too large: 5 MB maximum.", fr: "Fichier trop lourd : 5 Mo au maximum." }),
            );
            return;
        }
        setErreur(null);
        setFichier(f);
    };
    const deposer = async () => {
        if (!fichier) return;
        setEnCours(true);
        const faute = await deposerUnDocument(fichier, mode).catch(() => "reseau");
        setEnCours(false);
        if (faute) {
            notifier.echec({ fr: "Envoi impossible. Vérifiez le fichier et réessayez.", en: "Upload failed. Check the file and try again." }, { reessayer: () => void deposer() });
            return;
        }
        notifier.succes({ fr: `Document « ${fichier.name} » envoyé. Analyse en cours.`, en: `Document "${fichier.name}" uploaded. Processing.` });
        apres();
        fermer();
    };

    return (
        <FenetreLibre
            ouverte
            fermer={fermer}
            titre={t({ en: "Drop a document", fr: "Déposer un document" })}
            corps={
                <div className="space-y-6 py-5" data-testid="fenetre-depot">
                    <ExternalProcessingNotice />
                    <div className="space-y-1.5">
                        <p className="text-sm">{t({ en: "File (PDF, Word, Markdown, text)", fr: "Fichier (PDF, Word, Markdown, texte)" })}</p>
                        <input ref={entree} type="file" accept=".pdf,.docx,.doc,.txt,.json,.md" className="hidden" data-depot-fichier onChange={(e) => choisir(e.target.files?.[0])} />
                        {fichier ? (
                            <div className="flex items-center gap-3 rounded-xl border p-3 text-sm">
                                <FileText className="size-5 text-muted-foreground" />
                                <span className="min-w-0 flex-1 truncate font-medium">{fichier.name}</span>
                                <span className="text-xs text-muted-foreground">{taille(fichier.size)}</span>
                                <Button variant="ghost" size="icon" aria-label={t({ en: "Remove the file", fr: "Retirer le fichier" })} onClick={() => setFichier(null)}>
                                    <X className="size-4" />
                                </Button>
                            </div>
                        ) : (
                            <button
                                type="button"
                                onClick={() => entree.current?.click()}
                                onDragOver={(e) => {
                                    e.preventDefault();
                                    setSurvol(true);
                                }}
                                onDragLeave={() => setSurvol(false)}
                                onDrop={(e) => {
                                    e.preventDefault();
                                    setSurvol(false);
                                    choisir(e.dataTransfer.files?.[0]);
                                }}
                                className={`flex w-full cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-sm text-muted-foreground hover:font-medium ${survol ? "border-foreground/40" : ""}`}
                            >
                                <Upload className="size-5" />
                                {t({ en: "Drag here or choose", fr: "Glisser ici ou choisir" })}
                            </button>
                        )}
                        {erreur && (
                            <p role="alert" className="text-xs text-destructive">
                                {erreur}
                            </p>
                        )}
                    </div>
                    <div className="space-y-1.5 border-t pt-5">
                        <p className="flex items-center gap-1.5 text-sm">
                            {t({ en: "Reading mode", fr: "Mode de lecture" })}
                            <Info>
                                {t({
                                    en: "Whole document: the agent reads everything, for a short text. Search by excerpts: the most relevant passages are retrieved, for a long document.",
                                    fr: "Document entier : l'agent lit tout, pour un texte court. Recherche par extraits : les passages les plus pertinents sont retrouvés, pour un document long.",
                                })}
                            </Info>
                        </p>
                        <Segmente valeur={mode === "full_document" ? entier : extraits} options={[entier, extraits]} changer={(v) => setMode(v === entier ? "full_document" : "chunked")} />
                    </div>
                </div>
            }
            actions={
                <>
                    <Button variant="outline" onClick={fermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button disabled={!fichier || enCours} onClick={() => void deposer()}>
                        {t({ en: "Drop", fr: "Déposer" })}
                    </Button>
                </>
            }
        />
    );
}
