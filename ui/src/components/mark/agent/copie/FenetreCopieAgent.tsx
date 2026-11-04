"use client";

/**
 * [.mark] U2 quinquies (E58, E33) : « Exporter vers un client » (Labo → client) et « Ramener au Labo » (client → Labo), UNE fenêtre
 * en trois temps, reprise de la maquette (`modale-export.tsx`) : 1) l'organisation (recherche et état) ; 2) ce que l'agent emporte,
 * une ligne par élément (copier, relier à l'existant, laisser vide) ; 3) le compte rendu et le lien vers l'agent copié.
 *
 * Tout vient du serveur (`/export-agent`) : les organisations que le rôle ouvre, le relevé des éléments et les choix permis, la copie.
 * L'agent arrive TOUJOURS en brouillon ; rien n'est publié ; l'original ne bouge pas ; les clés ne voyagent jamais (« relier » désigne
 * une clé de la cible par son nom). Une explication n'est jamais une phrase visible : elle est dans le « ! ».
 */
import { Check, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
    ciblesApiV1ExportAgentWorkflowIdCiblesGet,
    copierApiV1ExportAgentWorkflowIdCopierPost,
    releveApiV1ExportAgentWorkflowIdReleveGet,
} from "@/client/sdk.gen";
import type { CiblesResponse, CompteRendu, ElementReleve, Releve } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { retenirEspace } from "@/lib/espaceCourant";

import { adresseOnglet } from "../onglets-agent";

type Sens = "exporter" | "ramener";
type Action = "copier" | "relier" | "vide";
type Cible = CiblesResponse["cibles"][number];

const T = {
    titreExporter: { en: "Export to a client", fr: "Exporter vers un client" },
    titreRamener: { en: "Bring back to the Labo", fr: "Ramener au Labo" },
    vers: { en: "To", fr: "Vers" },
    depuis: { en: "From", fr: "Depuis" },
    emporte: { en: "what the agent takes along", fr: "ce que l'agent emporte" },
    termine: { en: "Agent copied", fr: "Agent copié" },
    infoExporter: {
        en: "A copy, never a link: the agent arrives as a draft at the client, with its tests if you want them, and nobody publishes it. The Labo's agent is not touched. Keys never travel.",
        fr: "Une copie, jamais un lien : l'agent arrive en brouillon chez le client, avec ses tests si vous le voulez, et n'est publié par personne. L'agent du Labo n'est pas touché. Les clés ne voyagent jamais.",
    },
    infoRamener: {
        en: "A copy as a draft, in the “Copies de clients” folder of the Labo. What belongs to the client stays with the client. Keys never travel.",
        fr: "Une copie en brouillon, dans le dossier « Copies de clients » du Labo. Ce qui appartient au client reste chez lui. Les clés ne voyagent jamais.",
    },
    chercher: { en: "Search an organization", fr: "Chercher une organisation" },
    aucune: { en: "No organization", fr: "Aucune organisation" },
    dejaCopie: { en: "Already copied", fr: "Déjà copié" },
    pasCopie: { en: "Not copied yet", fr: "Pas encore copié" },
    annuler: { en: "Cancel", fr: "Annuler" },
    continuer: { en: "Continue", fr: "Continuer" },
    retour: { en: "Back", fr: "Retour" },
    fermer: { en: "Close", fr: "Fermer" },
    element: { en: "Item", fr: "Élément" },
    chez: { en: "At", fr: "Chez" },
    tests: { en: "With its tests", fr: "Avec ses tests" },
    exporterBrouillon: { en: "Export as a draft", fr: "Exporter en brouillon" },
    ramenerBrouillon: { en: "Bring back as a draft", fr: "Ramener en brouillon" },
    copie: { en: "Copying…", fr: "Copie en cours…" },
    chargement: { en: "Reading the agent…", fr: "Lecture de l'agent…" },
    ouvrirChez: { en: "Open at", fr: "Ouvrir chez" },
    ouvrirLabo: { en: "Open in the Labo", fr: "Ouvrir au Labo" },
    deja: { en: "This agent was already copied there: nothing was written.", fr: "Cet agent est déjà copié là-bas : rien n'a été écrit." },
    brouillon: { en: "is there as a draft", fr: "est là, en brouillon" },
    testsCopies: { en: "tests carried", fr: "tests emportés" },
    copies: { en: "copied", fr: "copiés" },
    relies: { en: "linked", fr: "reliés" },
    vides: { en: "left empty", fr: "laissés vides" },
    secrets: { en: "secret values removed from the copy", fr: "valeurs secrètes retirées de la copie" },
    // Les choix
    copierChez: { en: "Copy at the client", fr: "Copier chez le client" },
    copierAuLabo: { en: "Copy to the Labo", fr: "Copier au Labo" },
    agentsDuGroupe: { en: "Agents of the group", fr: "Agents du groupe" },
    relier: { en: "Link to the existing one", fr: "Relier à l'existant" },
    reglerVide: { en: "Leave empty", fr: "Laisser vide" },
    relierA: { en: "Link to", fr: "Relier à" },
    suitAgent: { en: "Follows the copied agent", fr: "Suit l'agent copié" },
    horsGroupe: { en: "Points outside the group: left empty", fr: "Mène hors du groupe : laissé vide" },
    pasPret: { en: "Not ready: cannot be copied", fr: "Pas prêt : ne peut pas être copié" },
    jamaisCopiee: { en: "A key is never copied", fr: "Une clé n'est jamais copiée" },
    avecCle: { en: "Carries a key: link it at the target", fr: "Porte une clé : à relier chez la cible" },
    sansNumeros: { en: "The fiche follows, without its phone numbers", fr: "La fiche suit, sans ses numéros" },
    nomCopie: { en: "Name of the copy", fr: "Nom de la copie" },
    nomCopieAide: { en: "Empty: the agent's name followed by the client's.", fr: "Vide : le nom de l'agent suivi de celui du client." },
    dossierCopie: { en: "Folder of the Labo", fr: "Dossier du Labo" },
    dossierParDefaut: { en: "Copies de clients (default)", fr: "Copies de clients (par défaut)" },
    // Les sortes
    agent: { en: "Agent of the group", fr: "Agent du groupe" },
    outil: { en: "Tool", fr: "Outil" },
    document: { en: "Document", fr: "Document" },
    cle: { en: "Key", fr: "Clé" },
    enregistrement: { en: "Recording", fr: "Enregistrement" },
    etablissement: { en: "Establishment", fr: "Établissement" },
    echecLecture: { en: "The agent could not be read. Try again.", fr: "L'agent n'a pas pu être lu. Réessayez." },
    succes: { en: "Agent copied as a draft.", fr: "Agent copié en brouillon." },
    echecCopie: { en: "Copy impossible. Try again.", fr: "Copie impossible. Réessayez." },
    dejaNotif: { en: "Already copied: nothing was written.", fr: "Déjà copié : rien n'a été écrit." },
    ouvrir: { en: "Open the copy", fr: "Ouvrir la copie" },
} satisfies Record<string, Texte>;

const SORTES: Record<ElementReleve["type"], Texte> = {
    agent: T.agent,
    outil: T.outil,
    document: T.document,
    cle: T.cle,
    enregistrement: T.enregistrement,
    etablissement: T.etablissement,
};

const NOTES: Record<string, Texte> = {
    suit_l_agent: T.suitAgent,
    hors_du_groupe: T.horsGroupe,
    pas_pret: T.pasPret,
    jamais_copiee: T.jamaisCopiee,
    avec_cle: T.avecCle,
    sans_numeros: T.sansNumeros,
};

type Choix = Record<string, { action: Action; cible: string | null }>;
const cleDe = (e: Pick<ElementReleve, "type" | "ref">) => `${e.type}:${e.ref}`;

export function FenetreCopieAgent({ agentId, sens, fermer }: { agentId: number; nom?: string; sens: Sens; fermer: () => void }) {
    const { t } = useLangue();
    const router = useRouter();
    const [etape, setEtape] = useState<1 | 2 | 3>(1);
    const [cibles, setCibles] = useState<Cible[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [cherche, setCherche] = useState("");
    const [cible, setCible] = useState<Cible | null>(null);
    const [releve, setReleve] = useState<Releve | null>(null);
    const [choix, setChoix] = useState<Choix>({});
    const [avecTests, setAvecTests] = useState(true);
    const [nomDeLaCopie, setNomDeLaCopie] = useState(""); // A-7 : « Ramener », nom au choix (vide : le nom d'usage)
    const [dossierId, setDossierId] = useState(""); // A-7 : « Ramener », dossier du Labo (vide : « Copies de clients »)
    const [enCours, setEnCours] = useState(false);
    const [compte, setCompte] = useState<CompteRendu | null>(null);

    const libelleAction = (a: Action, _e: ElementReleve, cibleNom?: string) =>
        a === "copier" ? (sens === "exporter" ? t(T.copierChez) : t(T.copierAuLabo)) : a === "relier" ? (cibleNom ? `${t(T.relierA)} ${cibleNom}` : t(T.relier)) : t(T.reglerVide);

    // Étape 1 : les organisations que le rôle ouvre. Pour « Ramener », il n'y en a qu'une (le Labo) : on passe directement au relevé.
    useEffect(() => {
        let vivant = true;
        void ciblesApiV1ExportAgentWorkflowIdCiblesGet({ path: { workflow_id: agentId }, query: { sens } }).then((r) => {
            if (!vivant) return;
            if (r.error || !r.data) return setErreur(true);
            setCibles(r.data.cibles);
            if (sens === "ramener" && r.data.cibles.length === 1) void lireLeReleve(r.data.cibles[0]);
        });
        return () => {
            vivant = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [agentId, sens]);

    const lireLeReleve = useCallback(
        async (c: Cible) => {
            setCible(c);
            setReleve(null);
            setEtape(2);
            const r = await releveApiV1ExportAgentWorkflowIdReleveGet({ path: { workflow_id: agentId }, query: { sens, cible: c.id } });
            if (r.error || !r.data) {
                notifier.echec(T.echecLecture, { erreur: r.error, reessayer: () => void lireLeReleve(c), groupe: "copie-agent" });
                setEtape(sens === "ramener" ? 1 : 1);
                if (sens === "ramener") setErreur(true);
                return;
            }
            setReleve(r.data);
            setChoix(Object.fromEntries(r.data.elements.map((e) => [cleDe(e), { action: e.defaut as Action, cible: e.cible_par_defaut ?? null }])));
        },
        [agentId, sens],
    );

    // Comme la maquette : tous les agents du groupe sur UNE ligne ; les passations qui suivent les agents copiés ne s'y listent pas.
    const lignes = useMemo(() => {
        const elements = (releve?.elements ?? []).filter((e) => e.code !== "suit_l_agent");
        const agents = elements.filter((e) => e.type === "agent");
        if (agents.length === 0) return elements;
        const groupe: ElementReleve = { ...agents[0], ref: agents.map((a) => a.ref).join(","), nom: agents.map((a) => a.nom).join(" · ") };
        return [groupe, ...elements.filter((e) => e.type !== "agent")];
    }, [releve]);

    const visibles = useMemo(
        () => (cibles ?? []).filter((c) => c.nom.toLowerCase().includes(cherche.trim().toLowerCase())),
        [cibles, cherche],
    );

    const copier = async () => {
        if (!releve || !cible || enCours) return;
        setEnCours(true);
        const cours = notifier.enCours(T.copie, { groupe: "copie-agent" });
        try {
            const r = await copierApiV1ExportAgentWorkflowIdCopierPost({
                path: { workflow_id: agentId },
                // `nom` et `dossier_id` (SE-9, A-7) : acceptés par la route ; le client généré les reçoit au prochain passage du générateur.
                body: {
                    sens,
                    cible_organization_id: cible.id,
                    avec_tests: avecTests,
                    ...(sens === "ramener" ? { nom: nomDeLaCopie.trim() || null, dossier_id: dossierId ? Number(dossierId) : null } : {}),
                    choix: releve.elements.map((e) => {
                        const c = choix[cleDe(e)];
                        return { type: e.type, ref: e.ref, action: c.action, cible: c.action === "relier" ? c.cible : null };
                    }),
                },
            });
            if (r.error || !r.data) {
                cours.echec(T.echecCopie, { erreur: r.error, reessayer: () => void copier(), groupe: "copie-agent" });
                return;
            }
            setCompte(r.data);
            setEtape(3);
            if (r.data.deja_copie) cours.succes(T.dejaNotif, { groupe: "copie-agent" });
            else cours.succes(T.succes, { groupe: "copie-agent" });
        } catch (e) {
            cours.echec(T.echecCopie, { erreur: e, reessayer: () => void copier(), groupe: "copie-agent" });
        } finally {
            setEnCours(false);
        }
    };

    const ouvrirLaCopie = () => {
        if (!compte || !cible) return;
        // L'espace de l'onglet suit la copie : les adresses neutres (/agents/12) se lisent alors dans l'organisation de la cible.
        retenirEspace(sens === "ramener" ? "/labo" : `/clients/${cible.id}`);
        fermer();
        router.push(adresseOnglet(compte.agent_id, "parcours"));
    };

    const titre =
        etape === 3 ? t(T.termine) : etape === 2 && cible && sens === "exporter" ? `${t(T.vers)} ${cible.nom} : ${t(T.emporte)}` : sens === "exporter" ? t(T.titreExporter) : t(T.titreRamener);
    const comptes = compte
        ? {
              copier: compte.lignes.filter((l) => l.action === "copier").length,
              relier: compte.lignes.filter((l) => l.action === "relier").length,
              vide: compte.lignes.filter((l) => l.action === "vide").length,
          }
        : null;

    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {titre}
                        <Info>{sens === "exporter" ? t(T.infoExporter) : t(T.infoRamener)}</Info>
                    </DialogTitle>
                </div>

                <div className="min-h-0 flex-1 overflow-auto bg-background px-6 py-4">
                    {etape === 1 && (
                        <div className="space-y-3">
                            {erreur ? (
                                <EtatVide cas="erreur" reessayer={() => window.location.reload()} />
                            ) : cibles === null ? (
                                <EtatVide cas="chargement" lignes={3} />
                            ) : (
                                <>
                                    <div className="relative">
                                        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                                        <Input
                                            autoFocus
                                            value={cherche}
                                            onChange={(e) => setCherche(e.target.value)}
                                            placeholder={t(T.chercher)}
                                            aria-label={t(T.chercher)}
                                            className="h-9 pl-9"
                                        />
                                    </div>
                                    <div className="max-h-72 divide-y overflow-auto border-y">
                                        {visibles.map((c) => (
                                            <button
                                                key={c.id}
                                                type="button"
                                                onClick={() => setCible(c)}
                                                aria-pressed={cible?.id === c.id}
                                                className={`flex w-full cursor-pointer items-center gap-3 px-1 py-3 text-left text-sm hover:font-semibold ${cible?.id === c.id ? "bg-muted" : ""}`}
                                            >
                                                <span className="flex-1 font-medium">{c.nom}</span>
                                                <PointEtat etat={c.deja_copie ? "publie" : "brouillon"}>{c.deja_copie ? t(T.dejaCopie) : t(T.pasCopie)}</PointEtat>
                                                <span className="w-4">{cible?.id === c.id && <Check className="size-4" />}</span>
                                            </button>
                                        ))}
                                        {visibles.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">{t(T.aucune)}</p>}
                                    </div>
                                </>
                            )}
                        </div>
                    )}

                    {etape === 2 &&
                        (releve === null ? (
                            <EtatVide cas="chargement" lignes={4} />
                        ) : (
                            <div className="space-y-4">
                                {sens === "ramener" && (
                                    <div className="grid gap-3 border-b py-3.5 sm:grid-cols-2" data-ramener-destination>
                                        <div className="space-y-1 text-sm">
                                            <span className="block font-medium">{t(T.nomCopie)}</span>
                                            <Input
                                                aria-label={t(T.nomCopie)}
                                                value={nomDeLaCopie}
                                                maxLength={200}
                                                placeholder={`${releve.agent_nom} (…)`}
                                                onChange={(e) => setNomDeLaCopie(e.target.value)}
                                            />
                                            <span className="block text-xs text-muted-foreground">{t(T.nomCopieAide)}</span>
                                        </div>
                                        <div className="space-y-1 text-sm">
                                            <span className="block font-medium">{t(T.dossierCopie)}</span>
                                            <Liste
                                                valeur={dossierId}
                                                changer={setDossierId}
                                                vide={t(T.dossierParDefaut)}
                                                options={((releve as { dossiers?: { id: number; nom: string }[] }).dossiers ?? []).map((d) => ({ valeur: String(d.id), libelle: d.nom }))}
                                            />
                                        </div>
                                    </div>
                                )}
                                <table className="w-full text-sm">
                                    <thead className="border-b text-xs text-muted-foreground">
                                        <tr>
                                            <th className="py-2 text-left font-normal">{t(T.element)}</th>
                                            <th className="text-left font-normal">
                                                {t(T.chez)} {cible?.nom}
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                        {lignes.map((e) => {
                                            const c = choix[cleDe(e)];
                                            const note = e.code ? NOTES[e.code] : undefined;
                                            const unique = e.choix.length === 1;
                                            return (
                                                <tr key={cleDe(e)} data-element={cleDe(e).split(",")[0]}>
                                                    <td className="py-2.5 pr-3">
                                                        <span className="block text-xs text-muted-foreground">{e.type === "agent" && e.ref.includes(",") ? t(T.agentsDuGroupe) : t(SORTES[e.type])}</span>
                                                        {e.nom}
                                                    </td>
                                                    <td className="py-2.5">
                                                        {unique ? (
                                                            <span className="text-muted-foreground">
                                                                {note ? t(note) : libelleAction(e.choix[0] as Action, e)}
                                                            </span>
                                                        ) : (
                                                            <div className="space-y-1">
                                                                <Liste
                                                                    valeur={`${c?.action}|${c?.cible ?? ""}`}
                                                                    changer={(v) => {
                                                                        const [action, vers] = v.split("|");
                                                                        setChoix((x) => ({ ...x, [cleDe(e)]: { action: action as Action, cible: vers || null } }));
                                                                    }}
                                                                    className="max-w-72"
                                                                    options={e.choix.flatMap((a) =>
                                                                        a === "relier" && (e.cibles ?? []).length > 0
                                                                            ? (e.cibles ?? []).map((cb) => ({ valeur: `relier|${cb.ref}`, libelle: libelleAction("relier", e, cb.nom) }))
                                                                            : [{ valeur: `${a}|`, libelle: libelleAction(a as Action, e) }],
                                                                    )}
                                                                />
                                                                {note && <span className="block text-xs text-muted-foreground">{t(note)}</span>}
                                                            </div>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                                <div className="flex items-center gap-4 border-t py-3.5">
                                    <p className="flex-1 text-sm font-medium">
                                        {t(T.tests)} ({releve.nb_tests})
                                    </p>
                                    <Switch checked={avecTests} onCheckedChange={setAvecTests} aria-label={t(T.tests)} disabled={releve.nb_tests === 0} />
                                </div>
                            </div>
                        ))}

                    {etape === 3 && compte && comptes && (
                        <div className="space-y-2 py-2 text-sm">
                            {compte.deja_copie ? (
                                <p className="flex items-center gap-2">
                                    <Check className="size-4 text-(--point-publie)" /> {t(T.deja)}
                                </p>
                            ) : (
                                <>
                                    <p className="flex items-center gap-2">
                                        <Check className="size-4 text-(--point-publie)" /> {compte.agents.map((a) => a.nom).join(" · ")} {t(T.brouillon)}
                                        {avecTests ? `, ${compte.tests_copies} ${t(T.testsCopies)}` : ""}.
                                    </p>
                                    <p className="flex items-center gap-2">
                                        <Check className="size-4 text-(--point-publie)" /> {comptes.copier} {t(T.copies)}, {comptes.relier} {t(T.relies)}, {comptes.vide} {t(T.vides)}.
                                    </p>
                                    {compte.secrets_retires > 0 && (
                                        <p className="flex items-center gap-2">
                                            <Check className="size-4 text-(--point-publie)" /> {compte.secrets_retires} {t(T.secrets)}.
                                        </p>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </div>

                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {etape === 1 && (
                        <>
                            <Button variant="outline" onClick={fermer}>
                                {t(T.annuler)}
                            </Button>
                            <Button disabled={!cible} onClick={() => cible && void lireLeReleve(cible)}>
                                {t(T.continuer)}
                            </Button>
                        </>
                    )}
                    {etape === 2 && (
                        <>
                            {sens === "exporter" && (
                                <Button variant="outline" onClick={() => setEtape(1)}>
                                    {t(T.retour)}
                                </Button>
                            )}
                            {sens === "ramener" && (
                                <Button variant="outline" onClick={fermer}>
                                    {t(T.annuler)}
                                </Button>
                            )}
                            <Button disabled={!releve || enCours} onClick={() => void copier()}>
                                {sens === "exporter" ? t(T.exporterBrouillon) : t(T.ramenerBrouillon)}
                            </Button>
                        </>
                    )}
                    {etape === 3 && (
                        <>
                            <Button variant="outline" onClick={fermer}>
                                {t(T.fermer)}
                            </Button>
                            <Button onClick={ouvrirLaCopie}>
                                {sens === "exporter" ? `${t(T.ouvrirChez)} ${cible?.nom ?? ""}` : t(T.ouvrirLabo)}
                            </Button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
