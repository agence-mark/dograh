"use client";

/**
 * [.mark] U9 : l'accueil d'un client (`/clients/<org>`), repris de la maquette (`app/clients/[org]/page.tsx`) : ses agents, ses
 * branchements (base, après-appel, intégrations, téléphonie, clés) et ce qui reste à améliorer. Chaque ligne vient d'une route
 * réelle de CE client (l'organisation est celle de l'adresse) ; une lecture qui échoue se dit « illisible », jamais un état inventé.
 * « Ouvrir son portail » reste affiché désactivé, avec sa raison, tant que le portail n'existe pas.
 */
import { AudioLines, Check, Circle, Database, ExternalLink, Inbox, KeyRound, Phone, Plug, Workflow, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
    getApresAppelApiV1OrganizationsApresAppelGet,
    getBaseClientApiV1OrganizationsBaseClientGet,
    getConnexionsApiV1ConnecteursConnexionsGet,
    getWorkflowsSummaryApiV1WorkflowSummaryGet,
    listerLesClesApiV1ClesGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
    lireLaFileDeTriApiV1TriGet,
} from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { useNomEspace } from "@/components/mark/studio/nom-espace";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const T = {
    portail: { en: "Open its portal", fr: "Ouvrir son portail" },
    portailRaison: {
        en: "The portal does not exist yet.",
        fr: "Le portail n'existe pas encore.",
    },
    agents: { en: "Agents", fr: "Agents" },
    tous: { en: "All", fr: "Tous" },
    aucunAgent: { en: "No agent", fr: "Aucun agent" },
    branchements: { en: "Connections", fr: "Branchements" },
    base: { en: "Client database", fr: "Base du client" },
    apresAppel: { en: "After-call", fr: "Après-appel" },
    integrations: { en: "Integrations", fr: "Intégrations" },
    telephonie: { en: "Telephony", fr: "Téléphonie" },
    cles: { en: "Keys", fr: "Clés" },
    aAmeliorer: { en: "To improve", fr: "À améliorer" },
    rienAAmeliorer: { en: "Nothing to improve", fr: "Rien à améliorer" },
    illisible: { en: "unreadable", fr: "illisible" },
    pasRattachee: { en: "not attached", fr: "non rattachée" },
    injoignable: { en: "unreachable", fr: "injoignable" },
    rattachee: { en: "attached", fr: "rattachée" },
    nonRegle: { en: "not set", fr: "non réglé" },
    regle: { en: "set", fr: "réglé" },
    aucune: { en: "none", fr: "aucune" },
    aucun: { en: "none", fr: "aucun" },
    connexions: { en: "connection(s)", fr: "connexion(s)" },
    configurations: { en: "configuration(s)", fr: "configuration(s)" },
    cle: { en: "key(s)", fr: "clé(s)" },
    points: { en: "point(s) waiting", fr: "point(s) en attente" },
    chargement: { en: "Loading…", fr: "Lecture…" },
} satisfies Record<string, Texte>;

type Etat = { fait: boolean; texte: string } | "illisible" | null;
type Ligne = {
    id: string;
    icone: LucideIcon;
    titre: Texte;
    suite: string;
    etat: Etat;
};

export default function AccueilClient() {
    const { t } = useLangue();
    const { org } = useParams<{ org: string }>();
    const { user, loading: authLoading } = useAuth();
    const nom = useNomEspace("client", org ?? null);
    const [agents, setAgents] = useState<{ id: number; name: string }[] | null>(null);
    const [erreurAgents, setErreurAgents] = useState(false);
    const [lignes, setLignes] = useState<Ligne[]>([]);
    const [aAmeliorer, setAAmeliorer] = useState<number | "illisible" | null>(null);

    useEffect(() => {
        if (authLoading || !user) return;
        let vivant = true;
        // Une seule fois chaque lecture, toutes en parallèle (jamais en chaîne).
        void (async () => {
            const [ag, base, apres, connexions, telephonie, cles, tri] = await Promise.all([
                getWorkflowsSummaryApiV1WorkflowSummaryGet(),
                getBaseClientApiV1OrganizationsBaseClientGet(),
                getApresAppelApiV1OrganizationsApresAppelGet(),
                getConnexionsApiV1ConnecteursConnexionsGet(),
                listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet(),
                listerLesClesApiV1ClesGet(),
                lireLaFileDeTriApiV1TriGet(),
            ]);
            if (!vivant) return;
            if (ag.error || !Array.isArray(ag.data)) setErreurAgents(true);
            else setAgents(ag.data);
            setAAmeliorer(tri.error || !tri.data ? "illisible" : tri.data.lignes.length);
            const nb = (n: number, mot: Texte): Etat => ({
                fait: n > 0,
                texte: n > 0 ? `${n} ${t(mot)}` : t(T.aucune),
            });
            setLignes([
                {
                    id: "base",
                    icone: Database,
                    titre: T.base,
                    suite: "base",
                    etat:
                        base.error || !base.data
                            ? "illisible"
                            : base.data.nom_base
                              ? {
                                    fait: base.data.joignable !== false,
                                    texte: `${base.data.nom_base} · ${base.data.joignable === false ? t(T.injoignable) : t(T.rattachee)}`,
                                }
                              : { fait: false, texte: t(T.pasRattachee) },
                },
                {
                    id: "apres-appel",
                    icone: Workflow,
                    titre: T.apresAppel,
                    suite: "base",
                    etat:
                        apres.error || !apres.data
                            ? "illisible"
                            : {
                                  fait: apres.data.base_rattachee,
                                  texte: apres.data.base_rattachee ? t(T.regle) : t(T.nonRegle),
                              },
                },
                {
                    id: "integrations",
                    icone: Plug,
                    titre: T.integrations,
                    suite: "integrations",
                    etat: connexions.error || !connexions.data ? "illisible" : nb(connexions.data.connexions?.length ?? 0, T.connexions),
                },
                {
                    id: "telephonie",
                    icone: Phone,
                    titre: T.telephonie,
                    suite: "telephonie",
                    etat: telephonie.error || !telephonie.data ? "illisible" : nb(telephonie.data.configurations.length, T.configurations),
                },
                {
                    id: "cles",
                    icone: KeyRound,
                    titre: T.cles,
                    suite: "modeles",
                    etat: cles.error || !cles.data ? "illisible" : nb(cles.data.length, T.cle),
                },
            ]);
        })();
        return () => {
            vivant = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading, user]);

    const base = `/clients/${org}`;
    return (
        <PageStudio>
            <>
                <TitrePage
                    titre={nom ?? "…"}
                    action={
                        <Button variant="outline" size="sm" disabled title={t(T.portailRaison)}>
                            <ExternalLink className="size-3.5" /> {t(T.portail)}
                        </Button>
                    }
                />

                <section>
                    <div className="flex items-center pb-3">
                        <p className="flex-1 text-base font-semibold">{t(T.agents)}</p>
                        <Link href={`${base}/agents`} className="text-sm text-(--acc) hover:font-semibold">
                            {t(T.tous)}
                        </Link>
                    </div>
                    {erreurAgents ? (
                        <EtatVide cas="erreur" reessayer={() => window.location.reload()} />
                    ) : agents === null ? (
                        <EtatVide cas="chargement" lignes={2} />
                    ) : agents.length === 0 ? (
                        <EtatVide cas="premier" icone={AudioLines} titre={t(T.aucunAgent)} />
                    ) : (
                        <ul className="divide-y">
                            {agents.map((a) => (
                                <li key={a.id} className="flex items-center gap-3 py-3 text-sm">
                                    <AudioLines className="size-4 text-muted-foreground" />
                                    <Link href={`/agents/${a.id}`} className="flex-1 hover:font-semibold">
                                        {a.name}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section>
                    <p className="pb-3 text-base font-semibold">{t(T.branchements)}</p>
                    <ul className="divide-y">
                        {lignes.length === 0 && <li className="py-3 text-sm text-muted-foreground">{t(T.chargement)}</li>}
                        {lignes.map((l) => {
                            const Icone = l.icone;
                            const ok = l.etat !== null && l.etat !== "illisible" && l.etat.fait;
                            return (
                                <li key={l.id} data-branchement={l.id} className="flex items-center gap-3 py-3 text-sm">
                                    <Icone className="size-4 text-muted-foreground" />
                                    <Link href={`${base}/${l.suite}`} className="flex-1 hover:font-semibold">
                                        {t(l.titre)}
                                    </Link>
                                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                        {l.etat === "illisible" ? t(T.illisible) : l.etat?.texte}
                                        {ok ? (
                                            <Check className="size-4 text-(--point-publie)" />
                                        ) : (
                                            <Circle className="size-4 text-muted-foreground/40" />
                                        )}
                                    </span>
                                </li>
                            );
                        })}
                    </ul>
                </section>

                <section>
                    <div className="flex items-center pb-3">
                        <p className="flex-1 text-base font-semibold">{t(T.aAmeliorer)}</p>
                        <Link href={`${base}/a-ameliorer`} className="text-sm text-(--acc) hover:font-semibold">
                            {t(T.tous)}
                        </Link>
                    </div>
                    {aAmeliorer === null ? (
                        <EtatVide cas="chargement" lignes={1} />
                    ) : aAmeliorer === "illisible" ? (
                        <EtatVide cas="erreur" reessayer={() => window.location.reload()} />
                    ) : aAmeliorer === 0 ? (
                        <EtatVide cas="fait" titre={t(T.rienAAmeliorer)} />
                    ) : (
                        <p className="flex items-center gap-3 py-3 text-sm">
                            <Inbox className="size-4 text-muted-foreground" />
                            {aAmeliorer} {t(T.points)}
                        </p>
                    )}
                </section>
            </>
        </PageStudio>
    );
}
