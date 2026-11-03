"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot F7 (D116, D117) : la section « Objets » du thème
 * « Établissements », à côté des fiches et des phrases. Une carte cliquable par objet (libellé précédé du lieu pour
 * un objet d'établissement, nom technique en gris, description, « utilisé par » calculé, jauge), qui ouvre sa
 * modale centrée ; « Ajouter un objet » ouvre la même, vide. Le plafond (D112) est un champ de la section, avec son
 * propre bouton : il s'écrit dans la base du client, comme les objets (exception E6 de la base du client).
 *
 * Sans base rattachée, la section dit ce que le serveur répond et ne propose rien.
 */
import { Braces, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { getObjetsApiV1OrganizationsObjetsGet, putReglagesObjetsApiV1OrganizationsObjetsReglagesPut } from "@/client/sdk.gen";
import type { ObjetAgent, ObjetsAgent } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { SectionLue } from "../entreprise/section-lue";
import { useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { Info } from "../studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";
import { CreateurVariable } from "../variables/CreateurVariable";
import { JaugeObjet } from "./ModaleObjet";

/** Les champs de `ReglagesObjets` montrés par la section (l'inventaire les compare au client généré). */
export const CHAMPS_REGLAGES_OBJETS = ["plafond_caracteres"] as const;

export const useObjets = () => {
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<ObjetsAgent | null>(null);
    const [refus, setRefus] = useState<string | null>(null);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getObjetsApiV1OrganizationsObjetsGet();
        if (reponse.error) {
            setRefus(detailFromError(reponse.error, "Objects unreadable"));
            return;
        }
        setRefus(null);
        // Same rule as the fiches (`useResumeEtablissements`): an answer without a body is an empty list.
        setVue(reponse.data ?? { objets: [], plafond_caracteres: 3000 });
    }, []);
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);
    return { vue, refus, relire };
};

export const SectionObjets = ({ etablissements }: { etablissements: Array<{ id: string; nom: string }> }) => {
    const { t } = useLangue();
    const { vue, refus, relire } = useObjets();
    const [ouvert, setOuvert] = useState<ObjetAgent | "neuf" | null>(null);
    const enregistre = vue?.plafond_caracteres ?? 3000;
    const nomDu = (id?: string | null) => etablissements.find((e) => e.id === id)?.nom ?? id;

    const enregistrerPlafond = async (n: number) => {
        const reponse = await putReglagesObjetsApiV1OrganizationsObjetsReglagesPut({ body: { plafond_caracteres: n } });
        if (reponse.error) {
            notifier.echec({ fr: "Le plafond n'a pas été enregistré.", en: "The ceiling was not saved." }, { erreur: detailFromError(reponse.error, "Ceiling refused") });
            return;
        }
        notifier.succes({ fr: "Plafond enregistré.", en: "Ceiling saved." });
        await relire();
    };

    const genre = (o: ObjetAgent) =>
        o.forme === "liste"
            ? (o.colonnes ?? []).length > 1
                ? t({ en: "Table", fr: "Tableau" })
                : t({ en: "List", fr: "Liste" })
            : o.type === "nombre" || o.type === "montant"
              ? t({ en: "Number or amount", fr: "Nombre ou montant" })
              : o.type === "oui_non"
                ? t({ en: "Yes or no", fr: "Oui ou non" })
                : o.type === "date"
                  ? t({ en: "Date", fr: "Date" })
                  : t({ en: "Word or sentence", fr: "Mot ou phrase" });
    const contenu = (o: ObjetAgent) =>
        o.forme === "liste"
            ? (o.colonnes ?? []).length > 1
                ? `${(o.lignes ?? []).length} ${t({ en: "rows", fr: "lignes" })} · ${(o.colonnes ?? []).length} ${t({ en: "columns", fr: "colonnes" })}`
                : `${(o.lignes ?? []).length} ${t({ en: "items", fr: "éléments" })}`
            : o.valeur || t({ en: "empty", fr: "vide" });

    return (
        <div id="etablissement-objets" data-section="objets">
            <TitreTableau
                titre={t({ en: "Variables", fr: "Variables" })}
                info={
                    <Info>
                        {t({
                            en: "Business data the agent receives as {{technical name}}: a word, a number, a yes or no, a date, a list or a table. .mark creates them; the client keeps their content up to date in the portal.",
                            fr: "Des données métier que l'agent reçoit en {{nom technique}} : un mot, un nombre, un oui ou non, une date, une liste ou un tableau. .mark les crée ; le client en tient le contenu à jour dans le portail.",
                        })}
                    </Info>
                }
                action={
                    <Button variant="outline" size="sm" onClick={() => setOuvert("neuf")} data-testid="ajouter-objet" disabled={!vue}>
                        <Plus className="size-3.5" /> {t({ en: "Variable", fr: "Variable" })}
                    </Button>
                }
            />
            {refus ? (
                <p className="py-3 text-sm text-muted-foreground" data-testid="objets-refus">
                    {refus}
                </p>
            ) : !vue ? (
                <EtatVide cas="chargement" />
            ) : (vue.objets ?? []).length === 0 ? (
                <EtatVide cas="premier" icone={Braces} titre={t({ en: "No variable yet", fr: "Aucune variable" })} />
            ) : (
                <div data-testid="liste-objets">
                    <Tableau
                        colonnes={[
                            { titre: t({ en: "Variable", fr: "Variable" }) },
                            { titre: t({ en: "Kind", fr: "Genre" }) },
                            { titre: t({ en: "Value", fr: "Valeur" }) },
                            { titre: t({ en: "Scope", fr: "Portée" }) },
                            { titre: t({ en: "Used by", fr: "Utilisée par" }), droite: true },
                        ]}
                    >
                        {(vue.objets ?? []).map((o) => (
                            <Ligne key={o.id} onClick={() => setOuvert(o)}>
                                <Cellule principale sous={<span className="font-mono" data-objet={o.nom}>{`{{${o.nom}}}`}</span>}>
                                    {o.libelle}
                                </Cellule>
                                <Cellule>{genre(o)}</Cellule>
                                <Cellule>
                                    <span className="inline-flex items-center gap-2">
                                        {contenu(o)}
                                        <JaugeObjet taille={o.taille ?? 0} plafond={enregistre} />
                                    </span>
                                </Cellule>
                                <Cellule>{o.etablissement ? nomDu(o.etablissement) : t({ en: "the whole company", fr: "toute l'entreprise" })}</Cellule>
                                <Cellule droite>
                                    <span data-utilise-par>
                                        {(o.utilise_par ?? []).length > 0
                                            ? `${(o.utilise_par ?? []).length} ${t({ en: "agent", fr: "agent" })}${(o.utilise_par ?? []).length > 1 ? "s" : ""}`
                                            : t({ en: "no agent", fr: "aucun agent" })}
                                    </span>
                                </Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                </div>
            )}
            {vue && (
                <SectionLue
                    titre={t({ en: "Ceiling of a variable", fr: "Plafond d'une variable" })}
                    info={t({ en: "Characters of the text the agent receives; an object over it is not saved (here or in the portal).", fr: "Caractères du texte que reçoit l'agent ; un objet au-delà n'est pas enregistré (ici comme au portail)." })}
                    lignes={[[t({ en: "Ceiling", fr: "Plafond" }), `${enregistre.toLocaleString("fr-FR")} ${t({ en: "characters", fr: "caractères" })}`]]}
                    fenetre={{
                        titre: t({ en: "Ceiling of a variable", fr: "Plafond d'une variable" }),
                        sections: [{ champs: [{ id: "plafond", t: "nombre", l: t({ en: "Ceiling", fr: "Plafond" }), v: String(enregistre), min: 100, max: 50000, unite: t({ en: "characters", fr: "caractères" }), info: t({ en: "100 to 50,000, default 3,000.", fr: "100 à 50 000, 3 000 par défaut." }) }] }],
                    }}
                    verifier={(v) => {
                        const n = Number(v.plafond);
                        return Number.isInteger(n) && n >= 100 && n <= 50000 ? null : { plafond: t({ en: "Between 100 and 50,000 characters.", fr: "Entre 100 et 50 000 caractères." }) };
                    }}
                    onValider={(v) => void enregistrerPlafond(Number(v.plafond))}
                />
            )}
            {ouvert && (
                <CreateurVariable
                    objet={ouvert === "neuf" ? null : ouvert}
                    plafond={enregistre}
                    etablissements={etablissements}
                    onFermer={(change) => {
                        setOuvert(null);
                        if (change) void relire();
                    }}
                />
            )}
        </div>
    );
};
