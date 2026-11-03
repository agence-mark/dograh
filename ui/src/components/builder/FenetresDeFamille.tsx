"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): the two windows of a family. « New family »: a family made on screen is always
 * « provided » (the builder reads the content and writes it with its own actions) and holds free text; the code is not
 * touched. « Sheet »: what the family is, when to use it, how to write an element; read by the builder before it searches
 * or writes; editable for every family (the identity and the shape read by the code stay locked for a family of the code).
 */
import { toast } from "sonner";

import { creerUneFamilleApiV1BuilderBibliothequeFamillesPost, modifierUneFamilleApiV1BuilderBibliothequeFamillesFamillePut } from "@/client";
import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { detailFromError } from "@/lib/apiError";

import { GROUPES } from "./libelles";

const slugDe = (nom: string) =>
    nom
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 40);

export function FenetreNouvelleFamille({ ouverte, fermer, apres }: { ouverte: boolean; fermer: () => void; apres: (slug: string) => void }) {
    const { t } = useLangue();
    const groupes = Object.keys(GROUPES);
    return (
        <FenetreChamps
            ouverte={ouverte}
            fermer={fermer}
            titre={t({ en: "New family", fr: "Nouvelle famille" })}
            info={t({
                en: "A family made here holds free text and is read by the builder, which writes it with its own actions. A family that a mechanism must read or apply stays in the code.",
                fr: "Une famille créée ici contient du texte libre et se lit par le builder, qui l'écrit avec ses propres actions. Une famille qu'un mécanisme doit lire ou appliquer reste dans le code.",
            })}
            valider={t({ en: "Create the family", fr: "Créer la famille" })}
            sections={[
                {
                    champs: [
                        { id: "libelle", t: "texte", l: t({ en: "Name", fr: "Nom" }) },
                        {
                            id: "groupe",
                            t: "choix",
                            l: t({ en: "Group", fr: "Groupe" }),
                            o: groupes,
                            v: "guide",
                        },
                        { id: "description", t: "zone", l: t({ en: "What it is", fr: "Ce que c'est" }) },
                        { id: "quand", t: "zone", l: t({ en: "When to use it", fr: "Quand s'en servir" }) },
                        { id: "comment", t: "zone", l: t({ en: "How to write an element", fr: "Comment écrire un élément" }) },
                    ],
                },
            ]}
            onValider={async (v) => {
                const libelle = String(v.libelle).trim();
                const slug = slugDe(libelle);
                if (!slug) {
                    toast.error(t({ en: "Give the family a name.", fr: "Donnez un nom à la famille." }));
                    return;
                }
                const reponse = await creerUneFamilleApiV1BuilderBibliothequeFamillesPost({
                    body: {
                        slug,
                        libelle,
                        groupe: String(v.groupe),
                        fiche: { description: String(v.description), quand: String(v.quand), comment: String(v.comment) },
                    },
                });
                if (reponse.error) {
                    toast.error(detailFromError(reponse.error, t({ en: "The family was not created.", fr: "La famille n'a pas été créée." })));
                    return;
                }
                apres(slug);
            }}
        />
    );
}

export function FenetreFiche({ famille, fermer, apres }: { famille: VueFamille | null; fermer: () => void; apres: () => void }) {
    const { t } = useLangue();
    if (!famille) return null;
    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={t({ en: `Sheet of « ${famille.libelle} »`, fr: `Fiche de « ${famille.libelle} »` })}
            info={
                famille.du_code
                    ? t({
                          en: "A family of the code: its name, group and shape (read by a mechanism) are locked. Its sheet can be changed.",
                          fr: "Une famille du code : son nom, son groupe et sa forme (lue par un mécanisme) sont verrouillés. Sa fiche, elle, se modifie.",
                      })
                    : t({ en: "The builder reads this sheet before it searches or writes in the family.", fr: "Le builder lit cette fiche avant de chercher ou d'écrire dans la famille." })
            }
            valider={t({ en: "Save the sheet", fr: "Enregistrer la fiche" })}
            sections={[
                {
                    champs: [
                        { id: "description", t: "zone", l: t({ en: "What it is", fr: "Ce que c'est" }), v: famille.fiche?.description },
                        { id: "quand", t: "zone", l: t({ en: "When to use it", fr: "Quand s'en servir" }), v: famille.fiche?.quand },
                        { id: "comment", t: "zone", l: t({ en: "How to write an element", fr: "Comment écrire un élément" }), v: famille.fiche?.comment },
                    ],
                },
            ]}
            onValider={async (v) => {
                const reponse = await modifierUneFamilleApiV1BuilderBibliothequeFamillesFamillePut({
                    path: { famille: famille.slug },
                    body: { fiche: { description: String(v.description), quand: String(v.quand), comment: String(v.comment) } },
                });
                if (reponse.error) {
                    toast.error(detailFromError(reponse.error, t({ en: "The sheet was not saved.", fr: "La fiche n'a pas été enregistrée." })));
                    return;
                }
                apres();
            }}
        />
    );
}
