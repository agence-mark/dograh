"use client";

/**
 * [.mark] K4 : « Établissements » comme la maquette (`entreprise.tsx`, OngletEtablissements) : « Toute l'entreprise » en
 * lignes (adresse, annonce de fermeture, Tout fermer) avec « Modifier », puis le tableau des fiches (un clic ouvre la
 * fenêtre de CETTE fiche). « Créer par copie », « + Établissement », la reprise des fiches et les phrases gardent leurs
 * fenêtres d'avant. Mêmes routes, mêmes enregistrements.
 */
import { Building2, Copy, Plus } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import { ContexteLignes } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { ModaleCopieFiche } from "../parametres-organisation/ModaleCopieFiche";
import { ModaleEtablissements, useResumeEtablissements } from "../parametres-organisation/ModaleEtablissements";
import { ModalePhrases } from "../parametres-organisation/ModalePhrases";
import { ModaleReprise } from "../parametres-organisation/ModaleReprise";
import type { EtatPreferences } from "../parametres-organisation/preferences";
import { type ProprietesThemeOrganisation,ThemeEtablissementOrganisation } from "../parametres-organisation/ThemesOrganisation";
import { texteAdresse } from "../SectionAdresseEtablissement";
import type { EtatAnnonceOuverture } from "../SectionAnnonceOuverture";
import { EtatVide } from "../studio/etat-vide";
import { Info, PointEtat } from "../studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";
import { DerniereModificationFiche, useDernieresModifications } from "./derniere-modification";

type Props = Pick<ProprietesThemeOrganisation, "signaler"> & {
    preferences: EtatPreferences;
    annonce: EtatAnnonceOuverture;
};

export function OngletEtablissements({ signaler, preferences, annonce }: Props) {
    const { t } = useLangue();
    const liste = useResumeEtablissements();
    const modifications = useDernieresModifications();
    const [entrepriseOuverte, setEntrepriseOuverte] = useState(false);
    const etaitModifie = useRef(false);
    const [cle, setCle] = useState(0);
    const [fiche, setFiche] = useState<string | null>(null);
    const [copie, setCopie] = useState(false);
    const [reprise, setReprise] = useState(false);
    const [phrases, setPhrases] = useState(false);
    const fiches = liste.liste ?? [];
    const adresseOrganisation = preferences.enregistrees.adresse_etablissement ?? null;
    // ⚠️ Stable : le thème signale sa pastille dans un effet qui dépend de cette fonction et se défait quand elle change ;
    // une fonction neuve à chaque rendu faisait signaler / défaire / signaler sans fin dès qu'une saisie était en cours.
    const signalerFenetre = useCallback(
        (id: Parameters<typeof signaler>[0], modifie: boolean, erreur: boolean) => {
            // Un brouillon enregistré (modifié, puis plus modifié) ferme sa fenêtre ; un échec la laisse ouverte.
            if (etaitModifie.current && !modifie && !erreur) setEntrepriseOuverte(false);
            etaitModifie.current = modifie;
            signaler(id, modifie, erreur);
        },
        [signaler],
    );

    return (
        <>
            <ContexteLignes.Provider value={{ annuler: () => { setEntrepriseOuverte(false); setCle((n) => n + 1); } }}>
                <ThemeEtablissementOrganisation
                    key={cle}
                    ouvert={entrepriseOuverte}
                    onBasculer={() => setEntrepriseOuverte((v) => !v)}
                    ouvrir={() => setEntrepriseOuverte(true)}
                    signaler={signalerFenetre}
                    preferences={preferences}
                    annonce={annonce}
                />
            </ContexteLignes.Provider>

            <TitreTableau
                titre={t({ en: "Establishments", fr: "Établissements" })}
                info={
                    <Info>
                        {t({
                            en: "One fiche per place: every call that serves it (the agent that chooses it, or the number called) reads its hours, address, announcements, appointments, closing and transfer number alone; nothing is inherited.",
                            fr: "Une fiche par lieu : tout appel qui la sert (l'agent qui la choisit, ou le numéro appelé) en lit seuls les horaires, l'adresse, les annonces, les rendez-vous, la fermeture et le numéro de transfert ; rien n'est hérité.",
                        })}
                    </Info>
                }
                action={
                    <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setReprise(true)} data-testid="ouvrir-reprise">
                            {t({ en: "Take over the fiches", fr: "Reprendre les fiches" })}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setPhrases(true)} data-testid="ouvrir-phrases">
                            {t({ en: "Sentences", fr: "Phrases" })}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setCopie(true)} disabled={fiches.length === 0} data-testid="creer-par-copie">
                            <Copy className="size-3.5" /> {t({ en: "Create by copy", fr: "Créer par copie" })}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setFiche("nouveau")} data-testid="ajouter-etablissement">
                            <Plus className="size-3.5" /> {t({ en: "Establishment", fr: "Établissement" })}
                        </Button>
                    </div>
                }
            />
            {liste.illisible ? (
                <EtatVide cas="erreur" reessayer={() => void liste.relire()} />
            ) : liste.liste === null ? (
                <EtatVide cas="chargement" />
            ) : fiches.length === 0 ? (
                <EtatVide cas="premier" icone={Building2} titre={t({ en: "No establishment: every call behaves as before", fr: "Aucun établissement : chaque appel se comporte comme avant" })} />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Establishment", fr: "Établissement" }) },
                        { titre: t({ en: "Hours", fr: "Horaires" }) },
                        { titre: t({ en: "State", fr: "État" }) },
                        { titre: t({ en: "Transfer", fr: "Transfert" }), droite: true },
                    ]}
                >
                    {fiches.map((e) => {
                        const ferme = Boolean(e.etat_force) && e.etat_force !== "OUVERT";
                        return (
                            <Ligne key={e.id} onClick={() => setFiche(e.id)}>
                                <Cellule principale sous={e.adresse ? texteAdresse(e.adresse) : undefined}>
                                    {e.nom}
                                </Cellule>
                                <Cellule>{(e.horaires_ouverture ?? "").trim().split("\n").join(" ; ") || "—"}</Cellule>
                                <Cellule>
                                    <PointEtat etat={ferme ? "panne" : "publie"}>
                                        {e.etat_force
                                            ? `${t({ en: "forced", fr: "forcé" })} : ${e.etat_force.toLowerCase().replace("_", " ")}`
                                            : t({ en: "computed from the hours", fr: "calculé depuis les horaires" })}
                                    </PointEtat>
                                    <DerniereModificationFiche modification={modifications.parFiche[e.id]} />
                                </Cellule>
                                <Cellule droite>{e.numero_transfert || "—"}</Cellule>
                            </Ligne>
                        );
                    })}
                </Tableau>
            )}

            <ModaleEtablissements
                ouverte={fiche !== null}
                fiche={fiche ?? undefined}
                onFermer={(enregistre) => {
                    setFiche(null);
                    if (enregistre) {
                        void liste.relire();
                        void modifications.relire();
                    }
                }}
                adresseOrganisation={adresseOrganisation}
                annonceOrganisation={annonce.enregistre}
            />
            <ModaleCopieFiche
                ouverte={copie}
                fiches={fiches}
                sourceInitiale={fiches[0]?.id ?? ""}
                onFermer={(resultat) => {
                    setCopie(false);
                    if (!resultat) return;
                    void liste.relire();
                    void modifications.relire();
                    setFiche(resultat.etablissement.id);
                }}
            />
            <ModaleReprise
                ouverte={reprise}
                onFermer={(ecrit) => {
                    setReprise(false);
                    if (ecrit) void liste.relire();
                }}
            />
            <ModalePhrases ouverte={phrases} onFermer={() => setPhrases(false)} annonceOrganisation={annonce.enregistre} />
        </>
    );
}
