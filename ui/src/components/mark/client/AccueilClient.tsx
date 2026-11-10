"use client";

/**
 * [.mark] Partie 3, L5b (décision 16 de l'audit) : l'accueil d'un client est une PAGE DE PILOTAGE pour l'équipe .mark (le client ne
 * voit jamais Dograh). Colonne principale : « À faire maintenant », les chiffres de la période (7 jours par défaut), les motifs
 * d'appel, les agents ; un client pas encore en service montre sa liste d'installation à la place des chiffres. Colonne de droite :
 * les branchements (repliés si tout va bien), « Relation client » en petit, l'activité récente.
 *
 * Aucun chiffre n'est compté ici : une route assemble (`/vues-equipe/pilotage/<client>`, les calculs de Qualité, des alertes, de
 * « Prêt à publier » et des branches) et la page l'affiche. Les branchements restent lus sur leurs routes d'avant, toutes en
 * parallèle avec la route de pilotage ; les intégrations à reconnecter viennent de la même lecture des connexions (une seule
 * lecture par donnée). Une lecture qui échoue se dit « illisible », jamais un état inventé.
 * « Ouvrir son portail » (clôture D2, É16) : le bouton plein de la Relation clients ; sans adresse de portail réglée, il est grisé et dit pourquoi.
 */
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
    getApresAppelApiV1OrganizationsApresAppelGet,
    getBaseClientApiV1OrganizationsBaseClientGet,
    getConnexionsApiV1ConnecteursConnexionsGet,
    listerLesClesApiV1ClesGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
    pilotageDUnClientApiV1VuesEquipePilotageOrganizationIdGet,
} from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { NouveauClient } from "@/components/mark/studio/selecteur-espace";
import { useNomEspace } from "@/components/mark/studio/nom-espace";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { BoutonPortail } from "@/components/mark/relation/BoutonPortail";

import { ActiviteRecente, type Branchement, Branchements, RelationCompacte } from "./pilotage/ColonneDroite";
import { type ConnexionALire, blocsIllisibles, construireAFaire } from "./pilotage/a-faire";
import { ALaFaire, Agents, ChiffresDeLaPeriode, ListeInstallation, Motifs, SelecteurPeriode } from "./pilotage/Blocs";
import { T, texte } from "./pilotage/textes";
import { PERIODE_PAR_DEFAUT, type Periode, type PilotageClient } from "./pilotage/types";

type Lecture<D> = { data?: D; error?: unknown };
const illisible = (l: Lecture<unknown>) => Boolean(l.error) || !l.data;

/** Les cinq branchements, lus sur les routes de CE client : ce qui va bien, ce qu'il faut régler, et où. */
export function brancher(
    t: (x: Texte) => string,
    lus: {
        base: Lecture<{ nom_base?: string | null; joignable?: boolean | null }>;
        apres: Lecture<{ base_rattachee: boolean }>;
        connexions: Lecture<{ connexions?: ConnexionALire[] }>;
        telephonie: Lecture<{ configurations: unknown[] }>;
        cles: Lecture<unknown[]>;
    },
): Branchement[] {
    const nb = (n: number, mot: Texte) => (n > 0 ? `${n} ${t(mot)}` : t(T.aucune));
    const lignes: Branchement[] = [];
    const { base, apres, connexions, telephonie, cles } = lus;
    lignes.push({
        id: "base",
        titre: T.base,
        vers: "base",
        ...(illisible(base)
            ? { ok: false, etat: t(T.illisible) }
            : base.data?.nom_base
              ? { ok: base.data.joignable !== false, etat: `${base.data.nom_base} · ${base.data.joignable === false ? t(T.injoignable) : t(T.rattachee)}` }
              : { ok: false, etat: t(T.pasRattachee) }),
    });
    lignes.push({
        id: "apres-appel",
        titre: T.apresAppel,
        vers: "base",
        ...(illisible(apres) ? { ok: false, etat: t(T.illisible) } : { ok: Boolean(apres.data?.base_rattachee), etat: apres.data?.base_rattachee ? t(T.regle) : t(T.nonRegle) }),
    });
    const liste = connexions.data?.connexions ?? [];
    const casses = liste.filter((c) => (c.erreurs ?? 0) > 0).length;
    lignes.push({
        id: "integrations",
        titre: T.integrations,
        vers: "integrations",
        ...(illisible(connexions)
            ? { ok: false, etat: t(T.illisible) }
            : { ok: casses === 0, etat: casses > 0 ? t(texte(T.aReconnecterN, casses)) : nb(liste.length, T.connexions) }),
    });
    lignes.push({
        id: "telephonie",
        titre: T.telephonie,
        vers: "telephonie",
        ...(illisible(telephonie)
            ? { ok: false, etat: t(T.illisible) }
            : { ok: (telephonie.data?.configurations.length ?? 0) > 0, etat: nb(telephonie.data?.configurations.length ?? 0, T.configurations) }),
    });
    lignes.push({
        id: "cles",
        titre: T.cles,
        vers: "modeles",
        ...(illisible(cles) ? { ok: false, etat: t(T.illisible) } : { ok: (cles.data?.length ?? 0) > 0, etat: nb(cles.data?.length ?? 0, T.cle) }),
    });
    return lignes;
}

export default function AccueilClient() {
    const { t } = useLangue();
    const { org } = useParams<{ org: string }>();
    const { user, loading: authLoading } = useAuth();
    const nom = useNomEspace("client", org ?? null);
    const [periode, setPeriode] = useState<Periode>(PERIODE_PAR_DEFAUT);
    const [pilotage, setPilotage] = useState<PilotageClient | null>(null);
    const [erreur, setErreur] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [connexions, setConnexions] = useState<ConnexionALire[] | null>(null);
    const [branchements, setBranchements] = useState<Branchement[] | null>(null);
    const [installation, setInstallation] = useState(false);
    const dernier = useRef(0);
    const dejaLu = useRef(false);

    const lirePilotage = useCallback(
        async (p: Periode) => {
            const ce = ++dernier.current;
            setEnCours(true);
            const r = await pilotageDUnClientApiV1VuesEquipePilotageOrganizationIdGet({ path: { organization_id: Number(org) }, query: { periode: p } });
            if (ce !== dernier.current) return; // une période plus récente a été demandée
            setEnCours(false);
            if (r.error || !r.data) setErreur(true);
            else {
                setErreur(false);
                setPilotage(r.data);
            }
        },
        [org],
    );

    // Les branchements et la route de pilotage partent ensemble, une seule fois chacun ; seul un changement de période relit le pilotage.
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const [, base, apres, lesConnexions, telephonie, cles] = await Promise.all([
                lirePilotage(PERIODE_PAR_DEFAUT),
                getBaseClientApiV1OrganizationsBaseClientGet(),
                getApresAppelApiV1OrganizationsApresAppelGet(),
                getConnexionsApiV1ConnecteursConnexionsGet(),
                listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet(),
                listerLesClesApiV1ClesGet(),
            ]);
            setConnexions(illisible(lesConnexions) ? [] : (lesConnexions.data?.connexions ?? []));
            setBranchements(brancher(t, { base, apres, connexions: lesConnexions, telephonie, cles }));
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading, user]);

    const changerPeriode = (p: Periode) => {
        setPeriode(p);
        void lirePilotage(p);
    };

    const base = `/clients/${org}`;
    const items = useMemo(() => construireAFaire(pilotage, connexions), [pilotage, connexions]);
    const enService = pilotage?.en_service ?? true;

    return (
        <PageStudio>
            <div className="@container space-y-8">
                <TitrePage
                    titre={nom ?? "…"}
                    info={pilotage ? t(pilotage.en_service ? T.enService : T.enInstallation) : undefined}
                    action={
                        <div className="flex flex-wrap items-center gap-2">
                            {pilotage?.en_service && <SelecteurPeriode valeur={periode} changer={changerPeriode} />}
                            <BoutonPortail organisation={Number(org)} />
                        </div>
                    }
                />

                {erreur && pilotage === null ? (
                    <EtatVide cas="erreur" reessayer={() => void lirePilotage(periode)} />
                ) : (
                    <div className="grid gap-x-10 gap-y-10 @4xl:grid-cols-[minmax(0,1fr)_288px]">
                        <div className={`min-w-0 space-y-10 ${enCours && pilotage ? "opacity-70" : ""}`} aria-busy={enCours}>
                            <ALaFaire
                                items={items}
                                illisibles={blocsIllisibles(pilotage)}
                                chargement={pilotage === null || connexions === null}
                                base={base}
                                reprendre={() => setInstallation(true)}
                                reessayer={() => void lirePilotage(periode)}
                            />
                            {pilotage === null ? (
                                <EtatVide cas="chargement" lignes={3} />
                            ) : (
                                <>
                                    {enService ? (
                                        <>
                                            <ChiffresDeLaPeriode pilotage={pilotage} periode={periode} base={base} />
                                            <Motifs motifs={pilotage.motifs} jours={pilotage.jours} base={base} />
                                        </>
                                    ) : (
                                        <ListeInstallation pilotage={pilotage} reprendre={() => setInstallation(true)} />
                                    )}
                                    <Agents agents={pilotage.agents} base={base} />
                                </>
                            )}
                        </div>

                        <aside className="min-w-0 space-y-8">
                            <Branchements branchements={branchements} base={base} />
                            <RelationCompacte pilotage={pilotage} org={org} />
                            <ActiviteRecente pilotage={pilotage} />
                        </aside>
                    </div>
                )}
            </div>
            <NouveauClient
                ouvert={installation}
                onOuvert={(o) => {
                    setInstallation(o);
                    if (!o) void lirePilotage(periode);
                }}
                organisationAReprendre={Number(org)}
            />
        </PageStudio>
    );
}
