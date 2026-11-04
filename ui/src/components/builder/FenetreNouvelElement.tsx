"use client";

/**
 * [.mark] K5 (fidélité à la maquette, E49) : la fenêtre « Nouvel élément » : famille, sous-dossier (existant ou nouveau),
 * titre, contenu (« Écrire » ou « Déposer un fichier »), étiquettes, notes de version ; entre toujours en Candidat.
 * Une famille dont un mécanisme lit le contenu prend un objet JSON (le serveur refuse avec la raison un contenu hors
 * forme) ; les autres, du texte libre. « Vient d'une source extérieure » garde l'import avec son origine.
 */
import { useEffect, useState } from "react";

import {
    champsDUneFamilleApiV1BuilderBibliothequeFamillesFamilleChampsGet,
    creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost,
    creerUnElementApiV1BuilderBibliothequeFamillePost,
    importerApiV1BuilderBibliothequeImportPost,
    listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet,
    rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost,
} from "@/client";
import type { ChampDeFamille, VueEtiquette, VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Carte, ChampFenetre, FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ChoixEtiquettes } from "./ChoixEtiquettes";
import { DepotDeDocument, STRUCTUREES } from "./DepotDeDocument";

/**
 * Lot 14 (I-3) : le contenu d'une famille à forme imposée, construit depuis ses champs (lus sur le serveur) au lieu d'un
 * JSON écrit à la main. ``null`` + un message : un champ n'est pas lisible (liste d'objets mal formée).
 */
export function contenuDesChamps(champs: ChampDeFamille[], valeurs: Record<string, string>): { contenu: Record<string, unknown>; erreurs: Record<string, string> } {
    const contenu: Record<string, unknown> = {};
    const erreurs: Record<string, string> = {};
    for (const c of champs) {
        const brut = (valeurs[c.nom] ?? "").trim();
        if (!brut) continue;
        if (c.sorte === "nombre") {
            const n = Number(brut);
            if (Number.isFinite(n)) contenu[c.nom] = n;
            else erreurs[c.nom] = "nombre";
        } else if (c.sorte === "liste") contenu[c.nom] = brut.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
        else if (c.sorte === "objet") {
            try {
                contenu[c.nom] = JSON.parse(brut);
            } catch {
                erreurs[c.nom] = "json";
            }
        } else contenu[c.nom] = brut;
    }
    return { contenu, erreurs };
}

/** Exemple de contenu JSON : un code, jamais traduit. */
const EXEMPLE_JSON = '{\n  "texte": ""\n}';

const NOUVEAU = "__nouveau__";
const aujourdhui = () => new Date().toISOString().slice(0, 10);
const slugDe = (titre: string) =>
    titre
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 60);

interface Props {
    familles: VueFamille[];
    famille: string;
    dossier: string | null;
    etiquettes: VueEtiquette[];
    fermer: () => void;
    /** L'élément est créé (ou déposé) : la page relit sa liste et l'ouvre. */
    onCree: (famille: string, slug: string) => void;
    /** Un ré-import montre ce qui a changé : la fenêtre reste ouverte pour qu'on le lise, la page relit sa liste. */
    onRelire: () => void;
}

export function FenetreNouvelElement({ familles, famille: depart, dossier: dossierDepart, etiquettes, fermer, onCree, onRelire }: Props) {
    const { t } = useLangue();
    const [slug, setSlugFamille] = useState(familles.some((f) => f.slug === depart) ? depart : (familles[0]?.slug ?? ""));
    const f = familles.find((x) => x.slug === slug);
    const [dossiers, setDossiers] = useState<string[]>([]);
    const [dossier, setDossier] = useState(dossierDepart ?? "");
    const [nouveauDossier, setNouveauDossier] = useState(false);
    const [titre, setTitre] = useState("");
    const [fichier, setFichier] = useState(false);
    const [texte, setTexte] = useState("");
    const [posees, setPosees] = useState<string[]>([]);
    const [notes, setNotes] = useState("");
    const [exterieur, setExterieur] = useState(false);
    const [source, setSource] = useState("");
    const [licence, setLicence] = useState("");
    const [date, setDate] = useState(aujourdhui());
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [comparatif, setComparatif] = useState<{ ajoutees: number; retirees: number; identique: boolean; diff: string } | null>(null);
    const structuree = STRUCTUREES.includes(slug);
    // Lot 14 (I-3) : les champs de la famille, lus sur le serveur ; sans eux (route en échec, forme libre), le JSON d'avant.
    const [champs, setChamps] = useState<ChampDeFamille[]>([]);
    const [valeurs, setValeurs] = useState<Record<string, string>>({});
    const [erreursChamps, setErreursChamps] = useState<Record<string, string>>({});
    const formulaire = structuree && champs.length > 0;

    useEffect(() => {
        let vivant = true;
        setChamps([]);
        setValeurs({});
        if (STRUCTUREES.includes(slug))
            void champsDUneFamilleApiV1BuilderBibliothequeFamillesFamilleChampsGet({ path: { famille: slug } }).then((r) => {
                if (vivant) setChamps(!r.error && r.data ? r.data : []);
            });
        return () => {
            vivant = false;
        };
    }, [slug]);

    useEffect(() => {
        let vivant = true;
        void listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet({ path: { famille: slug } }).then((r) => {
            if (vivant) setDossiers(!r.error && r.data ? r.data : []);
        });
        return () => {
            vivant = false;
        };
    }, [slug]);

    const pret = Boolean(f && titre.trim() && slugDe(titre) && (!exterieur || (source.trim() && licence.trim())));

    const creer = async () => {
        if (!f) return;
        let contenu: Record<string, unknown>;
        if (formulaire) {
            const lu = contenuDesChamps(champs, valeurs);
            setErreursChamps(lu.erreurs);
            if (Object.keys(lu.erreurs).length) return;
            contenu = lu.contenu;
        } else if (structuree) {
            try {
                const lu = JSON.parse(texte || "{}");
                if (typeof lu !== "object" || lu === null || Array.isArray(lu)) throw new Error("not an object");
                contenu = lu;
            } catch {
                setErreur(t({ en: "The content is not a valid JSON object.", fr: "Le contenu n'est pas un objet JSON valide." }));
                return;
            }
        } else {
            contenu = { texte };
        }
        const id = slugDe(titre);
        setEnCours(true);
        setErreur(null);
        const reponse = exterieur
            ? await importerApiV1BuilderBibliothequeImportPost({
                  body: { famille: slug, slug: id, titre: titre.trim(), contenu, origine: { source: source.trim(), licence: licence.trim(), date } },
              })
            : await creerUnElementApiV1BuilderBibliothequeFamillePost({ path: { famille: slug }, body: { slug: id, titre: titre.trim(), contenu, notes } });
        if (reponse.error || !reponse.data) {
            setEnCours(false);
            setErreur(echecAffiche(reponse.error));
            return;
        }
        const donnees = reponse.data as { comparatif?: unknown };
        if (exterieur && donnees.comparatif) {
            setComparatif(donnees.comparatif as { ajoutees: number; retirees: number; identique: boolean; diff: string });
            setEnCours(false);
            onRelire();
            return;
        }
        // Le rangement : sous-dossier (créé au besoin) et étiquettes, sans nouvelle version.
        const rangement: { dossier?: string; etiquettes?: string[] } = {};
        const chemin = dossier.trim().toLowerCase().replace(/\s+/g, "-");
        if (chemin) {
            if (nouveauDossier && !dossiers.includes(chemin)) {
                await creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost({ path: { famille: slug }, body: { chemin } });
            }
            rangement.dossier = chemin;
        }
        if (posees.length) rangement.etiquettes = posees;
        if (rangement.dossier || rangement.etiquettes) {
            const range = await rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost({ path: { famille: slug, slug: id }, body: rangement });
            if (range.error) notifier.avertissement({ fr: "Élément créé, mais pas rangé. Rangez-le depuis sa fiche.", en: "Element created, but not filed. File it from its sheet." });
        }
        setEnCours(false);
        notifier.succes({ fr: "Élément créé en Candidat.", en: "Element created as a Candidate." });
        onCree(slug, id);
    };

    return (
        <FenetreLarge
            testid="nouvel-element"
            fermer={fermer}
            titre={t({ en: "New element", fr: "Nouvel élément" })}
            sous={
                <span className="flex items-center gap-1.5">
                    {t({ en: "Enters as a Candidate", fr: "Entre en Candidat" })}
                    <Info>
                        {t({
                            en: "It becomes a Recipe when a bench has proven it and a person validates it.",
                            fr: "Il passe en Recette quand un banc l'a prouvé et qu'une personne le valide.",
                        })}
                    </Info>
                </span>
            }
            pied={
                <>
                    {erreur && (
                        <p role="alert" className="text-sm text-destructive">
                            {erreur}
                        </p>
                    )}
                    <span className="flex-1" />
                    <Button variant="outline" onClick={fermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    {!fichier && !comparatif && (
                        <Button disabled={!pret || enCours} onClick={() => void creer()}>
                            {exterieur ? t({ en: "Import as a Candidate", fr: "Importer en Candidat" }) : t({ en: "Create as a Candidate", fr: "Créer en Candidat" })}
                        </Button>
                    )}
                </>
            }
        >
            {comparatif && (
                <Carte titre={t({ en: "Changed since the last import", fr: "Changé depuis le dernier import" })}>
                    <div className="space-y-1 text-sm" data-testid="comparatif">
                        <p>
                            {comparatif.identique
                                ? t({ en: "Nothing changed since the last import.", fr: "Rien n'a changé depuis le dernier import." })
                                : t({
                                      en: `Changed since the last import: ${comparatif.ajoutees} line(s) added, ${comparatif.retirees} removed.`,
                                      fr: `Changé depuis le dernier import : ${comparatif.ajoutees} ligne(s) ajoutée(s), ${comparatif.retirees} retirée(s).`,
                                  })}
                        </p>
                        {!comparatif.identique && <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-xs">{comparatif.diff}</pre>}
                    </div>
                </Carte>
            )}
            <Carte>
                <div className="grid gap-3 sm:grid-cols-2">
                    <ChampFenetre titre={t({ en: "Family", fr: "Famille" })} info={f?.fiche?.description}>
                        <Liste
                            valeur={slug}
                            changer={(v) => {
                                setSlugFamille(v);
                                setDossier("");
                                setNouveauDossier(false);
                                setTexte("");
                            }}
                            options={familles.map((x) => ({ valeur: x.slug, libelle: x.libelle }))}
                            taille="default"
                            className="w-full"
                        />
                    </ChampFenetre>
                    <ChampFenetre titre={t({ en: "Sub-folder", fr: "Sous-dossier" })}>
                        {nouveauDossier ? (
                            <Input
                                autoFocus
                                value={dossier}
                                onChange={(e) => setDossier(e.target.value)}
                                aria-label={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                                placeholder={t({ en: "Sub-folder name", fr: "Nom du sous-dossier" })}
                            />
                        ) : (
                            <Liste
                                valeur={dossier}
                                changer={(v) => {
                                    if (v === NOUVEAU) {
                                        setDossier("");
                                        setNouveauDossier(true);
                                    } else setDossier(v);
                                }}
                                vide={t({ en: "None", fr: "Aucun" })}
                                options={[...dossiers, { valeur: NOUVEAU, libelle: t({ en: "New sub-folder…", fr: "Nouveau sous-dossier…" }) }]}
                                taille="default"
                                className="w-full"
                            />
                        )}
                    </ChampFenetre>
                </div>
                <ChampFenetre titre={t({ en: "Title", fr: "Titre" })}>
                    <Input value={titre} onChange={(e) => setTitre(e.target.value)} aria-label={t({ en: "Title", fr: "Titre" })} placeholder={t({ en: "Title of the element", fr: "Titre de l'élément" })} />
                </ChampFenetre>
            </Carte>
            <Carte
                titre={t({ en: "Content", fr: "Contenu" })}
                info={
                    structuree
                        ? t({ en: "This family is read by a mechanism: a JSON object, refused with the reason if it does not fit.", fr: "Cette famille est lue par un mécanisme : un objet JSON, refusé avec la raison s'il ne convient pas." })
                        : f?.fiche?.comment || t({ en: "Free text.", fr: "Texte libre." })
                }
            >
                {!structuree && (
                    <Segmente
                        valeur={fichier ? t({ en: "Drop a file", fr: "Déposer un fichier" }) : t({ en: "Write", fr: "Écrire" })}
                        options={[t({ en: "Write", fr: "Écrire" }), t({ en: "Drop a file", fr: "Déposer un fichier" })]}
                        changer={(v) => setFichier(v === t({ en: "Drop a file", fr: "Déposer un fichier" }))}
                    />
                )}
                {formulaire ? (
                    <div className="space-y-3" data-testid="champs-de-la-famille">
                        {champs.map((c) => (
                            <ChampFenetre
                                key={c.nom}
                                titre={`${c.nom.replace(/_/g, " ")}${c.obligatoire ? " *" : ""}`}
                                info={
                                    c.sorte === "liste"
                                        ? t({ en: "One item per line.", fr: "Un élément par ligne." })
                                        : c.sorte === "objet"
                                          ? t({ en: "A list or an object, written as JSON.", fr: "Une liste ou un objet, écrit en JSON." })
                                          : undefined
                                }
                            >
                                {c.sorte === "choix" ? (
                                    <Liste
                                        valeur={valeurs[c.nom] ?? ""}
                                        changer={(v) => setValeurs((x) => ({ ...x, [c.nom]: v }))}
                                        vide={t({ en: "None", fr: "Aucun" })}
                                        options={(c.choix ?? []).map((v) => ({ valeur: v, libelle: v }))}
                                        taille="default"
                                        className="w-full"
                                    />
                                ) : c.sorte === "texte" || c.sorte === "nombre" ? (
                                    <Input
                                        value={valeurs[c.nom] ?? ""}
                                        inputMode={c.sorte === "nombre" ? "numeric" : undefined}
                                        aria-label={c.nom.replace(/_/g, " ")}
                                        onChange={(e) => setValeurs((x) => ({ ...x, [c.nom]: e.target.value }))}
                                    />
                                ) : (
                                    <Textarea
                                        rows={c.sorte === "objet" ? 5 : 4}
                                        value={valeurs[c.nom] ?? ""}
                                        className={c.sorte === "objet" ? "font-mono text-xs" : ""}
                                        aria-label={c.nom.replace(/_/g, " ")}
                                        onChange={(e) => setValeurs((x) => ({ ...x, [c.nom]: e.target.value }))}
                                    />
                                )}
                                {erreursChamps[c.nom] && (
                                    <p role="alert" className="mt-1 text-xs text-destructive">
                                        {erreursChamps[c.nom] === "nombre"
                                            ? t({ en: "A number, please.", fr: "Un nombre, s'il vous plaît." })
                                            : t({ en: "Not valid JSON.", fr: "Ce n'est pas du JSON valide." })}
                                    </p>
                                )}
                            </ChampFenetre>
                        ))}
                    </div>
                ) : fichier && !structuree ? (
                    <DepotDeDocument
                        integre
                        familles={familles}
                        familleChoisie={slug}
                        // Le résultat du dépôt (Candidat, ou ce qui a changé) se lit ici : la fenêtre reste ouverte.
                        onDepose={() => onRelire()}
                    />
                ) : (
                    <Textarea
                        rows={structuree ? 10 : 8}
                        value={texte}
                        className={structuree ? "font-mono text-xs" : ""}
                        aria-label={structuree ? t({ en: "Content (JSON)", fr: "Contenu (JSON)" }) : t({ en: "Content", fr: "Contenu" })}
                        placeholder={structuree ? EXEMPLE_JSON : f?.fiche?.comment}
                        onChange={(e) => setTexte(e.target.value)}
                    />
                )}
            </Carte>
            {!fichier && (
                <Carte titre={t({ en: "Labels and notes", fr: "Étiquettes et notes" })}>
                    <ChoixEtiquettes posees={posees} existantes={etiquettes} changer={setPosees} />
                    <ChampFenetre
                        titre={t({ en: "Version notes", fr: "Notes de version" })}
                        info={t({ en: "What changes and why: visible in the history of the versions.", fr: "Ce qui change et pourquoi : visible dans l'historique des versions." })}
                    >
                        <Input value={notes} onChange={(e) => setNotes(e.target.value)} aria-label={t({ en: "Version notes", fr: "Notes de version" })} />
                    </ChampFenetre>
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={exterieur} onChange={(e) => setExterieur(e.target.checked)} />
                        <span>{t({ en: "It comes from a source outside .mark (import)", fr: "Cela vient d'une source extérieure à .mark (import)" })}</span>
                    </label>
                    {exterieur && (
                        <div className="grid gap-3 sm:grid-cols-3">
                            <ChampFenetre titre={t({ en: "Source (address or file)", fr: "Source (adresse ou fichier)" })}>
                                <Input value={source} onChange={(e) => setSource(e.target.value)} aria-label={t({ en: "Source (address or file)", fr: "Source (adresse ou fichier)" })} />
                            </ChampFenetre>
                            <ChampFenetre titre={t({ en: "Licence (or « unknown »)", fr: "Licence (ou « inconnue »)" })}>
                                <Input value={licence} onChange={(e) => setLicence(e.target.value)} aria-label={t({ en: "Licence (or « unknown »)", fr: "Licence (ou « inconnue »)" })} />
                            </ChampFenetre>
                            <ChampFenetre titre={t({ en: "Date", fr: "Date" })}>
                                <Input value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date" />
                            </ChampFenetre>
                        </div>
                    )}
                </Carte>
            )}
        </FenetreLarge>
    );
}
