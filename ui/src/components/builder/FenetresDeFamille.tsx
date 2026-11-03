"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49) puis K5 (fidélité à la maquette) : les deux fenêtres d'une famille, comme la
 * maquette (`FenetreFamille`) : Identité, « Fiche lue par le builder », « Forme du contenu ».
 * « Nouvelle famille » : une famille faite à l'écran est toujours « fournie » (le builder lit le contenu et l'écrit avec
 * ses actions) et porte du texte libre ; le code n'est pas touché. « Fiche » : ce qu'est la famille, quand s'en servir,
 * comment écrire un élément ; modifiable pour toute famille (l'identité et la forme lue par le code restent verrouillées
 * pour une famille du code).
 */
import { Lock } from "lucide-react";
import { useState } from "react";

import { creerUneFamilleApiV1BuilderBibliothequeFamillesPost, modifierUneFamilleApiV1BuilderBibliothequeFamillesFamillePut } from "@/client";
import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Carte, ChampFenetre, FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Liste } from "@/components/mark/studio/liste";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { GROUPES } from "./libelles";

const slugDe = (nom: string) =>
    nom
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 40);

function FicheLue({
    description,
    quand,
    comment,
    change,
}: {
    description: string;
    quand: string;
    comment: string;
    change: (champ: "description" | "quand" | "comment", v: string) => void;
}) {
    const { t } = useLangue();
    return (
        <Carte
            titre={t({ en: "Sheet read by the builder", fr: "Fiche lue par le builder" })}
            info={t({
                en: "The header of the family: the builder reads it before it searches or writes an element. It changes here or through the builder (a proposal accepted by a person).",
                fr: "L'en-tête de la famille : le builder le lit avant de chercher ou d'écrire un élément. Il se modifie ici ou par le builder (proposition acceptée par une personne).",
            })}
        >
            <ChampFenetre titre={t({ en: "Description", fr: "Description" })}>
                <Textarea
                    rows={2}
                    aria-label={t({ en: "Description", fr: "Description" })}
                    value={description}
                    onChange={(e) => change("description", e.target.value)}
                    placeholder={t({ en: "What the elements of this family are for.", fr: "À quoi servent les éléments de cette famille." })}
                />
            </ChampFenetre>
            <ChampFenetre titre={t({ en: "When to use it", fr: "Quand s'en servir" })}>
                <Textarea
                    rows={2}
                    aria-label={t({ en: "When to use it", fr: "Quand s'en servir" })}
                    value={quand}
                    onChange={(e) => change("quand", e.target.value)}
                    placeholder={t({ en: "When the builder must consult it.", fr: "À quel moment de la construction le builder doit la consulter." })}
                />
            </ChampFenetre>
            <ChampFenetre titre={t({ en: "How to write an element", fr: "Comment écrire un élément" })}>
                <Textarea
                    rows={3}
                    aria-label={t({ en: "How to write an element", fr: "Comment écrire un élément" })}
                    value={comment}
                    onChange={(e) => change("comment", e.target.value)}
                    placeholder={t({ en: "The writing rules of this family.", fr: "Les règles de rédaction propres à cette famille." })}
                />
            </ChampFenetre>
        </Carte>
    );
}

export function FenetreNouvelleFamille({ ouverte, fermer, apres }: { ouverte: boolean; fermer: () => void; apres: (slug: string) => void }) {
    const { t } = useLangue();
    const [libelle, setLibelle] = useState("");
    const [groupe, setGroupe] = useState("guide");
    const [fiche, setFiche] = useState({ description: "", quand: "", comment: "" });
    const [erreur, setErreur] = useState<string | null>(null);
    if (!ouverte) return null;
    const slug = slugDe(libelle.trim());

    const creer = async () => {
        if (!slug) return setErreur(t({ en: "Give the family a name.", fr: "Donnez un nom à la famille." }));
        const reponse = await creerUneFamilleApiV1BuilderBibliothequeFamillesPost({
            body: { slug, libelle: libelle.trim(), groupe, fiche },
        });
        if (reponse.error) {
            notifier.echec({ fr: "Famille non créée. Réessayez.", en: "Family not created. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Famille créée.", en: "Family created." });
        apres(slug);
        fermer();
    };

    return (
        <FenetreLarge
            fermer={fermer}
            titre={t({ en: "New family", fr: "Nouvelle famille" })}
            sous={t({ en: "The builder reads it through its sheet: no code to write.", fr: "Le builder la lit grâce à sa fiche : aucun code à écrire." })}
            pied={
                <>
                    <span className="flex-1" />
                    <Button variant="outline" onClick={fermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void creer()}>{t({ en: "Create the family", fr: "Créer la famille" })}</Button>
                </>
            }
        >
            <Carte titre={t({ en: "Identity", fr: "Identité" })}>
                <div className="grid gap-3 sm:grid-cols-2">
                    <ChampFenetre titre={t({ en: "Name", fr: "Nom" })}>
                        <Input
                            value={libelle}
                            aria-label={t({ en: "Name", fr: "Nom" })}
                            onChange={(e) => {
                                setLibelle(e.target.value);
                                setErreur(null);
                            }}
                            placeholder={t({ en: "e.g. Answers to objections", fr: "Ex. Réponses aux objections" })}
                        />
                        {erreur && (
                            <p role="alert" className="text-xs text-destructive">
                                {erreur}
                            </p>
                        )}
                    </ChampFenetre>
                    <ChampFenetre titre={t({ en: "Group", fr: "Groupe" })}>
                        <Liste
                            valeur={groupe}
                            changer={setGroupe}
                            options={Object.keys(GROUPES).map((g) => ({ valeur: g, libelle: t(GROUPES[g]) }))}
                            taille="default"
                            className="w-full"
                        />
                    </ChampFenetre>
                </div>
            </Carte>
            <FicheLue {...fiche} change={(champ, v) => setFiche({ ...fiche, [champ]: v })} />
            <Carte
                titre={t({ en: "Shape of the content", fr: "Forme du contenu" })}
                info={t({
                    en: "Free text: the builder reads it and writes it itself in the agent.",
                    fr: "Texte libre : le builder le lit et l'écrit lui-même dans l'agent.",
                })}
            >
                <p className="text-sm text-muted-foreground">{t({ en: "Free text (Markdown).", fr: "Texte libre (Markdown)." })}</p>
            </Carte>
        </FenetreLarge>
    );
}

export function FenetreFiche({ famille, fermer, apres }: { famille: VueFamille | null; fermer: () => void; apres: () => void }) {
    const { t } = useLangue();
    const [fiche, setFiche] = useState({
        description: famille?.fiche?.description ?? "",
        quand: famille?.fiche?.quand ?? "",
        comment: famille?.fiche?.comment ?? "",
    });
    if (!famille) return null;

    const enregistrer = async () => {
        const reponse = await modifierUneFamilleApiV1BuilderBibliothequeFamillesFamillePut({ path: { famille: famille.slug }, body: { fiche } });
        if (reponse.error) {
            notifier.echec({ fr: "Fiche non enregistrée. Réessayez.", en: "Sheet not saved. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Fiche enregistrée.", en: "Sheet saved." });
        apres();
        fermer();
    };

    return (
        <FenetreLarge
            fermer={fermer}
            titre={famille.libelle}
            sous={
                <span className="flex items-center gap-1.5">
                    {famille.du_code ? (
                        <>
                            <Lock className="size-3.5" /> {t({ en: "Family of the code", fr: "Famille du code" })} · {famille.slug}
                        </>
                    ) : (
                        <>
                            {t({ en: "Made on screen", fr: "Créée à l'écran" })} · {famille.slug}
                        </>
                    )}
                </span>
            }
            pied={
                <>
                    <span className="flex-1" />
                    <Button variant="outline" onClick={fermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()}>{t({ en: "Save the sheet", fr: "Enregistrer la fiche" })}</Button>
                </>
            }
        >
            <Carte
                titre={t({ en: "Identity", fr: "Identité" })}
                info={
                    famille.du_code
                        ? t({
                              en: "Name, group and target of a family of the code are fixed in familles.py: the code relies on them.",
                              fr: "Nom, groupe et cible d'une famille du code sont fixés dans familles.py : le code s'appuie dessus.",
                          })
                        : undefined
                }
            >
                <div className="grid gap-3 sm:grid-cols-2">
                    <ChampFenetre titre={t({ en: "Name", fr: "Nom" })}>
                        <p className="text-sm text-muted-foreground">{famille.libelle}</p>
                    </ChampFenetre>
                    <ChampFenetre titre={t({ en: "Group", fr: "Groupe" })}>
                        <p className="text-sm text-muted-foreground">{GROUPES[famille.groupe] ? t(GROUPES[famille.groupe]) : famille.groupe}</p>
                    </ChampFenetre>
                </div>
                <ChampFenetre
                    titre={t({ en: "What the builder does with it", fr: "Ce que le builder en fait" })}
                    info={t({ en: "The part of the agent where the content goes (prompts, links, tools…).", fr: "La partie de l'agent où le contenu va (ex. prompts de nœud, liaisons, outils)." })}
                >
                    <p className="text-sm text-muted-foreground">
                        {famille.cible}
                        {famille.mode === "applique" ? t({ en: " · applied by an action, without rewriting", fr: " · appliqué par une action, sans réécriture" }) : ""}
                    </p>
                </ChampFenetre>
            </Carte>
            <FicheLue {...fiche} change={(champ, v) => setFiche({ ...fiche, [champ]: v })} />
            <Carte
                titre={t({ en: "Shape of the content", fr: "Forme du contenu" })}
                info={
                    famille.du_code
                        ? t({ en: "Read or applied by the code: its fields are fixed in the code.", fr: "Lue ou appliquée par le code : ses champs sont fixés dans le code." })
                        : t({ en: "Free text: the builder reads it and writes it itself in the agent.", fr: "Texte libre : le builder le lit et l'écrit lui-même dans l'agent." })
                }
            >
                <p className="text-sm text-muted-foreground">
                    {famille.du_code ? t({ en: "Fixed by the code.", fr: "Fixée par le code." }) : t({ en: "Free text (Markdown).", fr: "Texte libre (Markdown)." })}
                </p>
            </Carte>
        </FenetreLarge>
    );
}
