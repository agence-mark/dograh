"use client";

/**
 * [.mark] K4 : « Équipe et routage » comme la maquette (`entreprise.tsx`, OngletEquipe) : deux tableaux nus (Personnes,
 * Routage par sujet) ; un clic sur une ligne ouvre la fenêtre de CETTE personne ou de CE sujet. Mêmes routes, mêmes
 * champs que l'ancienne fenêtre d'équipe (l'ancien thème d'équipe) : l'enregistrement renvoie l'équipe entière avec la ligne
 * changée (la route remplace tout), jamais une donnée inventée. L'écriture dit son résultat par `notifier`.
 */
import { Plus, Trash2, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    getChoixTraducteursApiV1ConnecteursTraducteursChoixGet,
    getEquipeApiV1OrganizationsEquipeGet,
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    getTraducteursApiV1ConnecteursTraducteursGet,
    putEquipeApiV1OrganizationsEquipePut,
} from "@/client/sdk.gen";
import type { Equipe, Etablissement, Personne, Sujet, TraducteurVue } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { identifiantPour } from "../parametres-organisation/ModaleEtablissements";
import { charge_utile_equipe, DESCRIPTION_MAX, lieuxDe } from "../parametres-organisation/charge-utile-equipe";
import { EtatVide } from "../studio/etat-vide";
import { FenetreChamps, type Valeurs } from "../studio/fenetre-champs";
import { Info, PointEtat } from "../studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";

const VIDE: Equipe = { personnes: [], sujets: [] };

const nomComplet = (p: Pick<Personne, "prenom" | "nom">) => [p.prenom, p.nom].filter(Boolean).join(" ");

function useEquipe() {
    const { user, loading: authLoading } = useAuth();
    const [equipe, setEquipe] = useState<Equipe | null>(null);
    const [etablissements, setEtablissements] = useState<Etablissement[]>([]);
    const [agenda, setAgenda] = useState<TraducteurVue | null>(null);
    const [illisible, setIllisible] = useState(false);
    const relire = useCallback(async () => {
        const [reponse, sites, choix, traducteurs] = await Promise.all([
            getEquipeApiV1OrganizationsEquipeGet(),
            getEtablissementsApiV1OrganizationsEtablissementsGet(),
            getChoixTraducteursApiV1ConnecteursTraducteursChoixGet(),
            getTraducteursApiV1ConnecteursTraducteursGet(),
        ]);
        setEtablissements(sites.data?.etablissements ?? []);
        setAgenda((traducteurs?.data ?? []).find((x) => x.systeme === choix?.data?.agenda) ?? null);
        setIllisible(Boolean(reponse.error) || !reponse.data);
        if (reponse.data) setEquipe(reponse.data);
    }, []);
    // [.mark] K4b : pas de lecture avant que l'authentification soit prête (sinon 401 et « Impossible de charger » à vie).
    useEffect(() => {
        if (authLoading || !user) return;
        void relire();
    }, [authLoading, user, relire]);
    const ecrire = useCallback(
        async (suivante: Equipe, succes: { fr: string; en: string }): Promise<boolean> => {
            const reponse = await putEquipeApiV1OrganizationsEquipePut({ body: charge_utile_equipe(suivante) });
            if (reponse.error) {
                notifier.echec({ fr: "L'équipe n'a pas été enregistrée.", en: "The team was not saved." }, { erreur: detailFromError(reponse.error, "Team not saved") });
                return false;
            }
            notifier.succes(succes);
            await relire();
            return true;
        },
        [relire],
    );
    return { equipe, etablissements, agenda, illisible, ecrire };
}

export function OngletEquipe({ baseRattachee }: { baseRattachee: boolean | null }) {
    const { t } = useLangue();
    const { equipe, etablissements, agenda, illisible, ecrire } = useEquipe();
    const [personne, setPersonne] = useState<Personne | "nouvelle" | null>(null);
    const [sujet, setSujet] = useState<Sujet | "nouveau" | null>(null);

    if (baseRattachee === false) {
        return (
            <div data-testid="equipe-sans-base">
                <EtatVide
                    cas="premier"
                    icone={Users}
                    titre={t({ en: "No database attached", fr: "Aucune base rattachée" })}
                    info={t({ en: "Attach the client's database first (Data and automations): the team lives there.", fr: "Rattachez d'abord la base du client (Base et automatisations) : l'équipe y vit." })}
                />
            </div>
        );
    }
    if (illisible) return <EtatVide cas="erreur" />;
    if (!equipe) return <EtatVide cas="chargement" />;

    const personnes = equipe.personnes ?? [];
    const sujets = equipe.sujets ?? [];
    const nomsEtabs = etablissements.map((e) => e.nom);
    const idEtab = (nom: string) => etablissements.find((e) => e.nom === nom)?.id ?? nom;
    const nomEtab = (id: string) => etablissements.find((e) => e.id === id)?.nom ?? id;
    const nomPersonne = (cle: string) => {
        const p = personnes.find((x) => x.cle === cle);
        return p ? nomComplet(p) : cle;
    };
    const clePersonne = (nom: string) => personnes.find((p) => nomComplet(p) === nom)?.cle ?? nom;
    const personneOuverte = personne && personne !== "nouvelle" ? personne : undefined;
    const sujetOuvert = sujet && sujet !== "nouveau" ? sujet : undefined;

    const enregistrerPersonne = async (valeurs: Valeurs) => {
        const lieux = ((valeurs.etablissements as string[]) ?? []).map(idEtab);
        const cle = personneOuverte?.cle ?? identifiantPour(`${valeurs.prenom || "personne"}-${valeurs.nom || ""}`, personnes.map((p) => p.cle));
        const ecrite: Personne = {
            ...(personneOuverte ?? { cle }),
            cle,
            prenom: String(valeurs.prenom),
            nom: String(valeurs.nom),
            role: String(valeurs.role),
            mail: String(valeurs.mail),
            telephone: String(valeurs.telephone),
            etablissements: lieux,
            etablissement: lieux[0] ?? null,
            destinataire_defaut: valeurs.defaut === true,
            actif: valeurs.actif === true,
            description: String(valeurs.description),
            joignable_par_transfert: valeurs.transfert === true,
            divulguer_telephone: valeurs.donneTel === true,
            divulguer_mail: valeurs.donneMail === true,
            ...(agenda ? { agendas: { ...(personneOuverte?.agendas ?? {}), [agenda.systeme]: String(valeurs.agenda ?? "") } } : {}),
        };
        const liste = personneOuverte ? personnes.map((p) => (p.cle === cle ? ecrite : p)) : [...personnes, ecrite];
        await ecrire({ ...equipe, personnes: liste }, { fr: "Personne enregistrée.", en: "Person saved." });
    };

    const enregistrerSujet = async (valeurs: Valeurs) => {
        const libelle = String(valeurs.sujet);
        const code =
            sujetOuvert?.code ??
            identifiantPour(libelle || "sujet", sujets.map((s) => s.code)).replace(/-/g, "_");
        const ecrit: Sujet = {
            ...(sujetOuvert ?? { code, actif: true }),
            code,
            libelle,
            urgent: valeurs.urgent === true,
            mots_declencheurs: String(valeurs.mots).split(","),
            destinataires: ((valeurs.recu as string[]) ?? []).map(clePersonne),
        };
        const liste = sujetOuvert ? sujets.map((s) => (s.code === code ? ecrit : s)) : [...sujets, ecrit];
        await ecrire({ ...equipe, sujets: liste }, { fr: "Sujet enregistré.", en: "Subject saved." });
    };

    const retirerSujet = (s: Sujet) =>
        notifier.annulable(
            { fr: "Sujet retiré.", en: "Subject removed." },
            { executer: () => ecrire({ ...(equipe ?? VIDE), sujets: sujets.filter((x) => x.code !== s.code) }, { fr: "Sujet retiré.", en: "Subject removed." }) },
        );

    const verifierPersonne = (v: Valeurs) => {
        const fautes: Record<string, string> = {};
        if (!String(v.prenom).trim()) fautes.prenom = t({ en: "A first name is required.", fr: "Le prénom est obligatoire." });
        if (String(v.description).trim().length > DESCRIPTION_MAX)
            fautes.description = t({ en: `At most ${DESCRIPTION_MAX} characters.`, fr: `${DESCRIPTION_MAX} caractères au plus.` });
        return Object.keys(fautes).length ? fautes : null;
    };

    return (
        <>
            <TitreTableau
                titre={t({ en: "People", fr: "Personnes" })}
                info={<Info>{t({ en: "Who works where. Written in the client's database; the client changes them from its portal.", fr: "Qui travaille où. Écrites dans la base du client ; le client les modifie depuis son portail." })}</Info>}
                action={
                    <Button variant="outline" size="sm" onClick={() => setPersonne("nouvelle")} data-testid="ajouter-personne">
                        <Plus className="size-3.5" /> {t({ en: "Person", fr: "Personne" })}
                    </Button>
                }
            />
            {personnes.length === 0 ? (
                <EtatVide cas="premier" icone={Users} titre={t({ en: "No one yet", fr: "Personne pour l'instant" })} compact />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Person", fr: "Personne" }) },
                        { titre: t({ en: "Establishments", fr: "Établissements" }) },
                        { titre: t({ en: "The agent may", fr: "L'agent peut" }) },
                        { titre: t({ en: "State", fr: "État" }), droite: true },
                    ]}
                >
                    {personnes.map((p) => {
                        const peut = [
                            p.joignable_par_transfert && t({ en: "transfer", fr: "transférer" }),
                            p.divulguer_telephone && t({ en: "give the phone", fr: "donner le téléphone" }),
                            p.divulguer_mail && t({ en: "give the e-mail", fr: "donner l'e-mail" }),
                        ].filter(Boolean);
                        return (
                            <Ligne key={p.cle} onClick={() => setPersonne(p)}>
                                <Cellule
                                    principale
                                    sous={`${p.role ?? ""}${p.destinataire_defaut ? `${p.role ? " · " : ""}${t({ en: "default recipient", fr: "destinataire par défaut" })}` : ""}` || undefined}
                                >
                                    {nomComplet(p)}
                                </Cellule>
                                <Cellule>{lieuxDe(p).length ? lieuxDe(p).map(nomEtab).join(", ") : t({ en: "the whole company", fr: "toute l'entreprise" })}</Cellule>
                                <Cellule>{peut.length ? peut.join(", ") : t({ en: "nothing", fr: "rien" })}</Cellule>
                                <Cellule droite>
                                    <PointEtat etat={p.actif === false ? "brouillon" : "publie"}>
                                        {p.actif === false ? t({ en: "deactivated", fr: "désactivée" }) : t({ en: "active", fr: "active" })}
                                    </PointEtat>
                                </Cellule>
                            </Ligne>
                        );
                    })}
                </Tableau>
            )}

            <TitreTableau
                titre={t({ en: "Routing by subject", fr: "Routage par sujet" })}
                info={<Info>{t({ en: "Who receives each subject after a call, in order. An urgent subject is flagged at the top of the mail.", fr: "Qui reçoit chaque sujet après un appel, dans l'ordre. Un sujet urgent est signalé en tête du mail." })}</Info>}
                action={
                    <Button variant="outline" size="sm" onClick={() => setSujet("nouveau")} data-testid="ajouter-sujet">
                        <Plus className="size-3.5" /> {t({ en: "Subject", fr: "Sujet" })}
                    </Button>
                }
            />
            {sujets.length === 0 ? (
                <EtatVide cas="premier" icone={Users} titre={t({ en: "No subject yet", fr: "Aucun sujet pour l'instant" })} compact />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Subject", fr: "Sujet" }) },
                        { titre: t({ en: "Trigger words", fr: "Mots déclencheurs" }) },
                        { titre: t({ en: "Received by, in order", fr: "Reçu par, dans l'ordre" }) },
                    ]}
                >
                    {sujets.map((s) => (
                        <Ligne key={s.code} onClick={() => setSujet(s)}>
                            <Cellule principale sous={s.urgent ? t({ en: "urgent", fr: "urgent" }) : undefined}>
                                {s.libelle}
                            </Cellule>
                            <Cellule>{(s.mots_declencheurs ?? []).join(", ")}</Cellule>
                            <Cellule>{(s.destinataires ?? []).map(nomPersonne).join(" → ")}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}

            <FenetreChamps
                ouverte={personne !== null}
                fermer={() => setPersonne(null)}
                titre={personne === "nouvelle" ? t({ en: "New person", fr: "Nouvelle personne" }) : personneOuverte ? nomComplet(personneOuverte) : ""}
                valider={t({ en: "Save", fr: "Enregistrer" })}
                verifier={verifierPersonne}
                onValider={(v) => void enregistrerPersonne(v)}
                sections={[
                    {
                        titre: t({ en: "Person", fr: "Personne" }),
                        champs: [
                            { id: "prenom", t: "texte", l: t({ en: "First name", fr: "Prénom" }), v: personneOuverte?.prenom ?? "" },
                            { id: "nom", t: "texte", l: t({ en: "Last name", fr: "Nom" }), v: personneOuverte?.nom ?? "" },
                            { id: "role", t: "texte", l: t({ en: "Role", fr: "Rôle" }), v: personneOuverte?.role ?? "" },
                            { id: "mail", t: "texte", l: t({ en: "E-mail", fr: "E-mail" }), v: personneOuverte?.mail ?? "" },
                            {
                                id: "telephone",
                                t: "texte",
                                l: t({ en: "Phone", fr: "Téléphone" }),
                                v: personneOuverte?.telephone ?? "",
                                info: t({ en: "No phone: the agent will pass the request on instead of transferring.", fr: "Pas de téléphone : l'agent transmettra la demande au lieu de transférer." }),
                            },
                            {
                                id: "etablissements",
                                t: "multi",
                                l: t({ en: "Establishments", fr: "Établissements" }),
                                o: nomsEtabs,
                                v: personneOuverte ? lieuxDe(personneOuverte).map(nomEtab) : [],
                                info: t({ en: "None ticked: the whole company.", fr: "Aucun coché : toute l'entreprise." }),
                            },
                            {
                                id: "defaut",
                                t: "inter",
                                l: t({ en: "Default recipient", fr: "Destinataire par défaut" }),
                                v: personneOuverte?.destinataire_defaut ?? false,
                                info: t({ en: "Receives the requests whose subject has no one.", fr: "Reçoit les demandes dont le sujet n'a personne." }),
                            },
                            {
                                id: "actif",
                                t: "inter",
                                l: t({ en: "Active", fr: "Active" }),
                                v: personneOuverte?.actif ?? true,
                                info: t({ en: "Someone removed is deactivated, never deleted: past requests keep their name.", fr: "Une personne retirée est désactivée, jamais supprimée : les demandes passées gardent son nom." }),
                            },
                        ],
                    },
                    {
                        titre: t({ en: "What the agent knows of her", fr: "Ce que l'agent sait d'elle" }),
                        info: t({ en: "Read by the agents whose « Team known to the agent » is on.", fr: "Lu par les agents dont « Équipe connue de l'agent » est allumé." }),
                        champs: [
                            {
                                id: "description",
                                t: "zone",
                                l: t({ en: "What this person takes care of", fr: "Ce dont cette personne s'occupe" }),
                                v: personneOuverte?.description ?? "",
                                info: t({ en: "In plain words: the agent reads it. Empty: the planner never books with this person.", fr: "En clair : l'agent le lit. Vide : le planificateur ne pose jamais de rendez-vous avec cette personne." }),
                            },
                            { id: "transfert", t: "inter", l: t({ en: "The agent may transfer a call to her", fr: "L'agent peut lui transférer un appel" }), v: personneOuverte?.joignable_par_transfert ?? false },
                            { id: "donneTel", t: "inter", l: t({ en: "The agent may give her phone", fr: "L'agent peut donner son téléphone" }), v: personneOuverte?.divulguer_telephone ?? false },
                            { id: "donneMail", t: "inter", l: t({ en: "The agent may give her e-mail", fr: "L'agent peut donner son e-mail" }), v: personneOuverte?.divulguer_mail ?? false },
                            ...(agenda
                                ? [
                                      {
                                          id: "agenda",
                                          t: "texte" as const,
                                          l: t({ en: `Agenda in ${agenda.libelle}`, fr: `Agenda dans ${agenda.libelle}` }),
                                          v: personneOuverte?.agendas?.[agenda.systeme] ?? "",
                                          info: `${t({ en: agenda.reference_agenda?.en ?? "", fr: agenda.reference_agenda?.fr ?? "" })}. ${t({ en: "Empty: the planner never books with this person.", fr: "Vide : le planificateur ne pose jamais de rendez-vous avec cette personne." })}`,
                                      },
                                  ]
                                : []),
                        ],
                    },
                ]}
            />

            <FenetreChamps
                ouverte={sujet !== null}
                fermer={() => setSujet(null)}
                titre={sujet === "nouveau" ? t({ en: "New subject", fr: "Nouveau sujet" }) : (sujetOuvert?.libelle ?? "")}
                valider={t({ en: "Save", fr: "Enregistrer" })}
                verifier={(v) => (String(v.sujet).trim() ? null : { sujet: t({ en: "A subject needs a name.", fr: "Un sujet a besoin d'un nom." }) })}
                onValider={(v) => void enregistrerSujet(v)}
                pied={
                    sujetOuvert ? (
                        <Button variant="ghost" size="sm" className="text-(--marque-danger-texte)" onClick={() => { const s = sujetOuvert; setSujet(null); retirerSujet(s); }}>
                            <Trash2 className="size-3.5" /> {t({ en: "Remove this subject", fr: "Retirer ce sujet" })}
                        </Button>
                    ) : undefined
                }
                sections={[
                    {
                        champs: [
                            { id: "sujet", t: "texte", l: t({ en: "Subject", fr: "Sujet" }), v: sujetOuvert?.libelle ?? "" },
                            { id: "urgent", t: "inter", l: t({ en: "Urgent", fr: "Urgent" }), v: sujetOuvert?.urgent ?? false },
                            {
                                id: "mots",
                                t: "texte",
                                l: t({ en: "Trigger words", fr: "Mots déclencheurs" }),
                                v: (sujetOuvert?.mots_declencheurs ?? []).join(", "),
                                info: t({ en: "Separated by commas.", fr: "Séparés par des virgules." }),
                            },
                            {
                                id: "recu",
                                t: "multi",
                                l: t({ en: "Received by, in order", fr: "Reçu par, dans l'ordre" }),
                                o: personnes.map(nomComplet),
                                v: (sujetOuvert?.destinataires ?? []).map(nomPersonne),
                                info: t({ en: "The order of the clicks is the order: the first receives, the next if the first is absent.", fr: "L'ordre des clics fait l'ordre : le premier reçoit, le suivant si le premier est absent." }),
                            },
                        ],
                    },
                ]}
            />
        </>
    );
}
