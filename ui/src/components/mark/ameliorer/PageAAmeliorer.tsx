"use client";

/**
 * [.mark] U8 : « À améliorer », la boucle (reprise de `components/studio/a-ameliorer.tsx` de la maquette, E9 et E23).
 * Une boîte de réception par état (À trier, En cours, Testée, Publiée), « Pannes et alertes » et, quand des vrais appels attendent
 * Claude Code, « À juger » (visible dès que le juge des vrais appels est sur Claude Code, comme la maquette, ou tant que des éléments
 * attendent). Tableau nu : Gravité · Problème · Fréquence · Relevé par · Cause probable. Un clic ouvre le détail.
 * Tout vient des routes `/ameliorations`, `/alertes` : aucune donnée écrite ici. Les requêtes d'une page partent en parallèle.
 */
import { useCallback, useEffect, useState } from "react";

import {
    lireLaFileAJugerApiV1AmeliorationsAJugerGet,
    lireLesAlertesApiV1AlertesGet,
    lireLesAmeliorationsApiV1AmeliorationsGet,
} from "@/client";
import type { LigneAJuger, LigneDAlerte, PageDAmeliorations } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { useSources } from "@/components/mark/sources/useSources";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Gravite, Info } from "@/components/mark/studio/marques";
import { useOngletDeLAdresse } from "@/components/mark/studio/onglets-page";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { TYPES_D_ALERTE } from "@/components/mark/tri/libelles";
import { useAuth } from "@/lib/auth";

import { DetailProbleme } from "./DetailProbleme";
import { AUTEUR, CAUSES, ETATS, type EtatDeLEcran, RELEVE_PAR, texteDeFrequence, titreLisible } from "./libelles";

type Vue = PageDAmeliorations["lignes"][number];
type Charge<T> = { etat: "chargement" } | { etat: "erreur" } | { etat: "acces" } | { etat: "pret"; donnees: T };

/** Une lecture refusée (403 : pas le droit de voir les conversations) montre « accès », pas une erreur à réessayer. */
const refus = (r: { error?: unknown; response?: { status?: number } }) => (r.error ? (r.response?.status === 403 ? ({ etat: "acces" } as const) : ({ etat: "erreur" } as const)) : null);

const T = {
    titre: { en: "To improve", fr: "À améliorer" },
    info: {
        en: "Problems raised by the judge, the code, the tests and the team; identical cases are grouped and counted.",
        fr: "Problèmes relevés par le juge, le code, les tests et l'équipe ; les cas identiques sont regroupés et comptés.",
    },
    pannes: { en: "Failures and alerts", fr: "Pannes et alertes" },
    aJuger: { en: "To judge", fr: "À juger" },
    gravite: { en: "Severity", fr: "Gravité" },
    probleme: { en: "Problem", fr: "Problème" },
    frequence: { en: "Frequency", fr: "Fréquence" },
    releve: { en: "Raised by", fr: "Relevé par" },
    cause: { en: "Probable cause", fr: "Cause probable" },
    rien: { en: "Nothing to improve", fr: "Rien à améliorer" },
    aucunePanne: { en: "No failure", fr: "Aucune panne" },
    rienAJuger: { en: "Nothing to judge", fr: "Rien à juger" },
    quand: { en: "When", fr: "Quand" },
    panne: { en: "Failure", fr: "Panne" },
    agent: { en: "Agent", fr: "Agent" },
    prevenu: { en: "Warned", fr: "Prévenu" },
    duree: { en: "Duration", fr: "Durée" },
    motif: { en: "Reason", fr: "Motif" },
    type: { en: "Kind", fr: "Genre" },
    appel: { en: "Call", fr: "Appel" },
    test: { en: "Test", fr: "Test" },
    mailEnvoye: { en: "mail sent", fr: "mail envoyé" },
    mailNon: { en: "mail not sent", fr: "mail non envoyé" },
    infoAJuger: {
        en: "Real calls kept waiting: they are judged with /juger in Claude Code.",
        fr: "Les vrais appels rangés en attente : on les traite avec /juger dans Claude Code.",
    },
};

const dateCourte = (iso: string | null | undefined, langue: string) =>
    iso ? new Date(iso).toLocaleString(langue === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";

const secondes = (s: number | null | undefined) => (s == null ? "" : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`);

export function PageAAmeliorer() {
    const { t, langue } = useLangue();
    const { user, loading } = useAuth();
    const ids = [...ETATS.map((e) => e.id), "pannes", "a_juger"];
    const { actif, choisir } = useOngletDeLAdresse(ids, "a_trier");
    const [liste, setListe] = useState<Charge<PageDAmeliorations>>({ etat: "chargement" });
    const [pannes, setPannes] = useState<Charge<LigneDAlerte[]>>({ etat: "chargement" });
    const [aJuger, setAJuger] = useState<Charge<LigneAJuger[]>>({ etat: "chargement" });
    const [ouvert, setOuvert] = useState<number | null>(null);
    const { sources } = useSources();

    const chargerLesPannes = useCallback(async () => {
        setPannes({ etat: "chargement" });
        const p = await lireLesAlertesApiV1AlertesGet();
        setPannes(refus(p) ?? (!p.data ? { etat: "erreur" } : { etat: "pret", donnees: p.data.lignes }));
    }, []);

    const chargerLaFile = useCallback(async () => {
        setAJuger({ etat: "chargement" });
        const j = await lireLaFileAJugerApiV1AmeliorationsAJugerGet();
        setAJuger(refus(j) ?? (!j.data ? { etat: "erreur" } : { etat: "pret", donnees: j.data }));
    }, []);

    const chargerLaListe = useCallback(async (etat: EtatDeLEcran) => {
        setListe({ etat: "chargement" });
        const r = await lireLesAmeliorationsApiV1AmeliorationsGet({ query: { etat } });
        setListe(refus(r) ?? (!r.data ? { etat: "erreur" } : { etat: "pret", donnees: r.data }));
    }, []);

    useEffect(() => {
        if (loading || !user) return;
        void (async () => {
            // Les compteurs « Pannes » et « À juger » et la liste de l'onglet courant partent ensemble.
            const [p, j] = await Promise.all([lireLesAlertesApiV1AlertesGet(), lireLaFileAJugerApiV1AmeliorationsAJugerGet()]);
            setPannes(refus(p) ?? (!p.data ? { etat: "erreur" } : { etat: "pret", donnees: p.data.lignes }));
            setAJuger(refus(j) ?? (!j.data ? { etat: "erreur" } : { etat: "pret", donnees: j.data }));
        })();
    }, [loading, user]);

    const etatCourant = ETATS.find((e) => e.id === actif)?.id;
    useEffect(() => {
        if (loading || !user || !etatCourant) return;
        void chargerLaListe(etatCourant);
    }, [loading, user, etatCourant, chargerLaListe]);

    const compteur = (id: string) => {
        if (id === "pannes") return pannes.etat === "pret" ? pannes.donnees.length : null;
        if (id === "a_juger") return aJuger.etat === "pret" ? aJuger.donnees.length : null;
        return liste.etat === "pret" ? (liste.donnees.compteurs[id] ?? 0) : null;
    };
    // E104 : l'onglet existe quand le juge des vrais appels est sur Claude Code (même vide : « Rien à juger »), ou tant que des éléments attendent.
    const aDesAppelsAJuger = sources?.juge_appels === "claude_code" || (aJuger.etat === "pret" && aJuger.donnees.length > 0);
    const onglets = [...ETATS.map((e) => ({ id: e.id as string, titre: t(e.libelle) })), { id: "pannes", titre: t(T.pannes) }, ...(aDesAppelsAJuger ? [{ id: "a_juger", titre: t(T.aJuger) }] : [])];
    const courant = actif === "a_juger" && !aDesAppelsAJuger ? "a_trier" : actif;

    return (
        <PageStudio>
            <TitrePage titre={t(T.titre)} info={t(T.info)} />
            <div role="tablist" className="flex items-center gap-1 border-b">
                {onglets.map((o) => {
                    const n = compteur(o.id);
                    return (
                        <button
                            key={o.id}
                            type="button"
                            role="tab"
                            aria-selected={courant === o.id}
                            onClick={() => choisir(o.id)}
                            className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm ${courant === o.id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"}`}
                        >
                            {o.titre} {n !== null && <span className="text-xs text-muted-foreground">{n}</span>}
                        </button>
                    );
                })}
            </div>
            {courant === "a_juger" ? (
                <TableDesAppelsAJuger charge={aJuger} t={t} langue={langue} reessayer={() => void chargerLaFile()} />
            ) : courant === "pannes" ? (
                <TableDesPannes charge={pannes} t={t} langue={langue} reessayer={() => void chargerLesPannes()} />
            ) : (
                <TableDesProblemes charge={liste} t={t} ouvrir={setOuvert} reessayer={() => etatCourant && void chargerLaListe(etatCourant)} />
            )}
            {ouvert !== null && (
                <DetailProbleme
                    id={ouvert}
                    fermer={() => setOuvert(null)}
                    apres={() => etatCourant && void chargerLaListe(etatCourant)}
                />
            )}
        </PageStudio>
    );
}

function TableDesProblemes({ charge, t, ouvrir, reessayer }: { charge: Charge<PageDAmeliorations>; t: ReturnType<typeof useLangue>["t"]; ouvrir: (id: number) => void; reessayer: () => void }) {
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={reessayer} />;
    const lignes = charge.donnees.lignes;
    if (lignes.length === 0) return <EtatVide cas="fait" titre={t(T.rien)} />;
    return (
        <Tableau colonnes={[{ titre: t(T.gravite) }, { titre: t(T.probleme) }, { titre: t(T.frequence) }, { titre: t(T.releve) }, { titre: t(T.cause) }]}>
            {lignes.map((p) => (
                <Ligne key={p.id} onClick={() => ouvrir(p.id)}>
                    <td className="w-28 py-3">
                        <Gravite n={p.gravite as 1 | 2 | 3} />
                    </td>
                    <Cellule className="!text-foreground" sous={`${p.workflow_nom}${p.version ? ` · v${p.version}` : ""}`}>
                        <span className="inline-flex items-center gap-1.5 font-medium">
                            {(() => {
                                const titre = titreLisible(p);
                                return typeof titre === "string" ? titre : t(titre);
                            })()}
                            <Info>{t(AUTEUR[p.releve_par] ?? AUTEUR.code)}</Info>
                        </span>
                    </Cellule>
                    <Cellule>{texteDeFrequence(p, t)}</Cellule>
                    <Cellule>{RELEVE_PAR[p.releve_par] ? t(RELEVE_PAR[p.releve_par]) : p.releve_par}</Cellule>
                    <Cellule>{p.cause && CAUSES[p.cause] ? t(CAUSES[p.cause]) : ""}</Cellule>
                </Ligne>
            ))}
        </Tableau>
    );
}

function TableDesPannes({ charge, t, langue, reessayer }: { charge: Charge<LigneDAlerte[]>; t: ReturnType<typeof useLangue>["t"]; langue: string; reessayer: () => void }) {
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={reessayer} />;
    if (charge.donnees.length === 0) return <EtatVide cas="fait" titre={t(T.aucunePanne)} />;
    return (
        <Tableau colonnes={[{ titre: t(T.quand) }, { titre: t(T.panne) }, { titre: t(T.agent) }, { titre: t(T.prevenu) }]}>
            {charge.donnees.map((a) => (
                <Ligne key={`${a.run_id}-${a.id}`} href={`/workflow/${a.workflow_id}/run/${a.run_id}`}>
                    <Cellule principale>{dateCourte(a.heure ?? a.cree_le, langue)}</Cellule>
                    <Cellule>
                        {TYPES_D_ALERTE[a.type] ? t(TYPES_D_ALERTE[a.type]) : a.type}
                        {a.detail ? ` : ${a.detail}` : ""}
                    </Cellule>
                    <Cellule>{a.workflow_nom}</Cellule>
                    <Cellule>{a.mail === "envoye" || a.mail === "deja_notifiee" ? t(T.mailEnvoye) : t(T.mailNon)}</Cellule>
                </Ligne>
            ))}
        </Tableau>
    );
}

function TableDesAppelsAJuger({ charge, t, langue, reessayer }: { charge: Charge<LigneAJuger[]>; t: ReturnType<typeof useLangue>["t"]; langue: string; reessayer: () => void }) {
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={reessayer} />;
    if (charge.donnees.length === 0) return <EtatVide cas="fait" titre={t(T.rienAJuger)} info={t(T.infoAJuger)} />;
    return (
        <>
            <p className="flex items-center gap-1.5 text-sm font-medium">
                {t(T.aJuger)}
                <Info>{t(T.infoAJuger)}</Info>
            </p>
            <Tableau colonnes={[{ titre: t(T.agent) }, { titre: t(T.quand) }, { titre: t(T.duree), droite: true }, { titre: t(T.motif) }]}>
                {charge.donnees.map((a) => (
                    <Ligne key={a.id} href={a.run_id && a.workflow_id ? `/workflow/${a.workflow_id}/run/${a.run_id}` : undefined}>
                        <Cellule principale sous={a.type === "test" ? `${t(T.test)} ${a.test ?? ""}` : undefined}>
                            {a.workflow_nom}
                        </Cellule>
                        <Cellule>{dateCourte(a.le, langue)}</Cellule>
                        <Cellule droite>{secondes(a.duree)}</Cellule>
                        <Cellule>{a.motif ?? ""}</Cellule>
                    </Ligne>
                ))}
            </Tableau>
        </>
    );
}
