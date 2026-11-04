"use client";

/**
 * [.mark] V2b (E51) : le tableau des clés de « Modèles et clés », comme la maquette : tableau nu « Clé · Sert à »,
 * « Ajouter une clé » en fenêtre, un clic sur une ligne ouvre la clé (où elle sert, et la supprimer).
 *
 * Les usages de TOUTES les clés viennent d'une seule lecture (`/cles/usages`), jamais une lecture par clé. La valeur
 * d'une clé n'est jamais lue ni affichée ; une suppression demande confirmation et dit où la clé servait.
 */
import { KeyRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { supprimerUneCleApiV1ClesUuidDelete, usagesDeToutesLesClesApiV1ClesUsagesGet } from "@/client";
import type { Cle, Usage } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Info } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";

import { DESCRIPTION_BIBLIOTHEQUE, FormulaireAjoutCle, nomDu } from "./FenetreCles";

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
    sert: { en: "Used for", fr: "Sert à" },
    nulle: { en: "nowhere", fr: "nulle part" },
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
    const { t } = useLangue();
    const usages = useUsages(cles);
    const [ajout, setAjout] = useState(false);
    const [ouverte, setOuverte] = useState<Cle | null>(null);

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
                <Tableau colonnes={[{ titre: t(T.cle) }, { titre: t(T.sert) }]}>
                    {cles.map((c) => {
                        const ici = usages?.[c.uuid];
                        const dit = ici === undefined ? "" : ici.length ? [...new Set(ici.map((u) => t(texteUsageCourt(u))))].join(" · ") : t(T.nulle);
                        return (
                            <Ligne key={c.uuid} onClick={() => setOuverte(c)}>
                                <Cellule principale>{c.nom}</Cellule>
                                <Cellule>{dit}</Cellule>
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
                valider={t(T.fermer)}
                etroite
                corps={<FormulaireAjoutCle sansCadre onAjoutee={async () => {
                    setAjout(false);
                    await apresChangement();
                }} />}
            />
            {ouverte && (
                <FenetreDeLaCle
                    cle={ouverte}
                    usages={usages?.[ouverte.uuid] ?? null}
                    fermer={() => setOuverte(null)}
                    apresSuppression={apresChangement}
                />
            )}
        </div>
    );
}

function FenetreDeLaCle({
    cle,
    usages,
    fermer,
    apresSuppression,
}: {
    cle: Cle;
    usages: Usage[] | null;
    fermer: () => void;
    apresSuppression: () => Promise<void>;
}) {
    const { t } = useLangue();
    const [confirme, setConfirme] = useState(false);
    const [enCours, setEnCours] = useState(false);

    const supprimer = async () => {
        setEnCours(true);
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

    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={cle.nom}
            sections={[]}
            valider={t(T.fermer)}
            etroite
            corps={
                <section className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                        {cle.nom_fournisseur ? `${cle.nom_fournisseur} · ` : ""}
                        {nomDu(cle.fournisseur)}
                        {cle.adresse ? ` · ${cle.adresse}` : ""}
                    </p>
                    <p className="text-sm font-semibold">{t(T.sert)}</p>
                    {usages === null ? (
                        <EtatVide cas="chargement" />
                    ) : usages.length === 0 ? (
                        <p className="text-sm text-muted-foreground">{t(T.nulle)}</p>
                    ) : (
                        <ul className="divide-y text-sm">
                            {usages.map((u) => (
                                <li key={`${u.ou}-${u.nom ?? ""}`} className="py-2">
                                    {t(texteUsageCourt(u))}
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
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
