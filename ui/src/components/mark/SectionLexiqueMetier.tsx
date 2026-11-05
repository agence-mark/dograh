"use client";

import { BookOpen, Check, Download, Plus, Search, Square, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  budgetLexiqueApiV1OrganizationsLexiqueBudgetPost,
  getLexiqueApiV1OrganizationsLexiqueGet,
  importLexiqueApiV1OrganizationsLexiqueImportPost,
  saveLexiqueApiV1OrganizationsLexiquePut,
} from "@/client/sdk.gen";
import type { BudgetLexique, LexiqueMetier, TermeLexique } from "@/client/types.gen";
import { useFormeMaquette } from "@/components/mark/ecran/forme-maquette";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Info } from "@/components/mark/studio/marques";
import { Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";

/**
 * [.mark] The organization's trade vocabulary (plan lexique-metier, L1, L3).
 *
 * One vocabulary per organization, used by every agent that has the switch on:
 * the ticked terms are listened for by the transcription, the names are
 * corrected before the model reads them, and « Say it as » changes how the
 * voice pronounces them.
 *
 * 🔑 Import brings a template of the socle (one per trade); export takes the
 * improvements back to it. An import never overwrites a term already there.
 *
 * 🆕 18/09 : the list is edited in a DIALOG, not inline on the settings page. A
 * trade holds a couple of hundred names (181 for the stove trade), and that many
 * rows of six controls buried every other card of the page. The dialog also
 * gives room for what a list that size needs: a search box, and one click to
 * tick or untick what the search shows (decision of Evan, 2026-09-18). The
 * dialog edits a COPY: closing it changes nothing, saving sends the copy.
 *
 * 🆕 26/09 (plan « le lexique », Q2, Q4): two boxes per term, « Listen for it »
 * (sent to the transcription) and « The business offers it » (what the agent
 * says the business offers, {{lexique_propose}}). And the budget of the list,
 * « 81 / 100 terms (Deepgram) » on Flux, « 212 / 500 tokens (Deepgram) » on
 * nova-3 (the probe of 26/09), with the ticked terms left out, is asked of
 * the API for the organization's provider: ⛔ the screen never counts on its
 * own, and no ceiling is written here.
 */

/** Mirrors `api/schemas/lexique_metier.py` (tenu égal par un test d'écran). */
const SEUIL_MOTS_COURANTS_DEFAUT = 10_000;
const SEUIL_MOTS_COURANTS_MIN = 1_000;
const SEUIL_MOTS_COURANTS_MAX = 31_796;

/** Wait this long after the last change of the draft before asking the budget again. */
const ATTENTE_BUDGET_MS = 300;

// V4 : la nature d'un terme, comme la maquette (Marque / Nom propre / Mot du métier). Un terme d'avant ce champ n'a que son type :
// un nom se lit « Marque » (le lexique sert d'abord à reconnaître les marques), un mot « Mot du métier ».
type Nature = NonNullable<TermeLexique["nature"]>;
const NATURES: Array<{ id: Nature; nom: Texte }> = [
  { id: "marque", nom: { en: "Brand", fr: "Marque" } },
  { id: "nom_propre", nom: { en: "Proper name", fr: "Nom propre" } },
  { id: "mot_du_metier", nom: { en: "Trade word", fr: "Mot du métier" } },
];
const natureDe = (terme: Pick<TermeLexique, "type" | "nature"> | undefined): Nature =>
  terme?.nature ?? (terme?.type === "mot" ? "mot_du_metier" : "marque");

const TERME_VIDE: TermeLexique = {
  terme: "",
  variantes: [],
  prononciation: null,
  type: "nom",
  categorie: null,
  a_ecouter: true,
  // ⛔ Not offered until someone ticks it: the agent never says the business
  // offers a name nobody said it does (question 182).
  propose: false,
};

function versTexte(variantes: Array<string> | undefined): string {
  return (variantes ?? []).join(", ");
}

function versVariantes(texte: string): Array<string> {
  return texte
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

/** Search without accents or case: « jotul » finds « Jøtul », « poele » finds « poêle ». */
function sansAccent(texte: string): string {
  return texte
    .toLowerCase()
    .replace(/ø/g, "o")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function correspond(terme: TermeLexique, recherche: string): boolean {
  if (!recherche) return true;
  const champs = [
    terme.terme,
    ...(terme.variantes ?? []),
    terme.prononciation ?? "",
    terme.categorie ?? "",
  ];
  return champs.some((champ) => sansAccent(champ).includes(recherche));
}

export function SectionLexiqueMetier() {
  const maquette = useFormeMaquette();
  const { t } = useLangue();
  const [terme, setTerme] = useState<number | "nouveau" | null>(null);
  const [seuilOuvert, setSeuilOuvert] = useState(false);
  const [lexique, setLexique] = useState<LexiqueMetier>({ termes: [] });
  const [chargement, setChargement] = useState(true);
  const [enregistrement, setEnregistrement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [lu, setLu] = useState(false);
  const [ouvert, setOuvert] = useState(false);
  // La copie de travail du dialogue : fermer la jette, enregistrer l'envoie.
  const [brouillon, setBrouillon] = useState<LexiqueMetier>({ termes: [] });
  const [recherche, setRecherche] = useState("");
  // Le budget de ce qui est enregistré (la carte) et du brouillon (le dialogue).
  const [budget, setBudget] = useState<BudgetLexique | null>(null);
  const [budgetDuBrouillon, setBudgetDuBrouillon] = useState<BudgetLexique | null>(null);
  const fichier = useRef<HTMLInputElement>(null);
  const { user, loading: authLoading } = useAuth();
  const dejaLu = useRef(false);

  // ⛔ Convention of the repository: the token is attached only once auth is
  // loaded. Reading before that sends an unauthenticated request that fails in
  // silence, and the screen would show an empty vocabulary.
  useEffect(() => {
    if (authLoading || !user || dejaLu.current) return;
    dejaLu.current = true;
    void charger();
  }, [authLoading, user]);

  async function charger() {
    setChargement(true);
    try {
      const reponse = await getLexiqueApiV1OrganizationsLexiqueGet();
      if (reponse.error || !reponse.data) {
        // ⛔ Enregistrer remplace TOUT le lexique : tant qu'on n'a pas lu ce qui
        // existe, on ne laisse pas écraser (relecture indépendante du 17/09).
        setLu(false);
        setErreur(
          echecAffiche(reponse.error, ECHECS.lexiqueLire),
        );
        return;
      }
      setLexique(reponse.data);
      setLu(true);
      setErreur(null);
    } catch {
      setLu(false);
      setErreur("Failed to load the trade vocabulary");
    } finally {
      setChargement(false);
    }
  }

  /** Ask the API what the transcription would receive; null when it cannot say. */
  async function demanderBudget(pour: LexiqueMetier): Promise<BudgetLexique | null> {
    try {
      const reponse = await budgetLexiqueApiV1OrganizationsLexiqueBudgetPost({ body: pour });
      if (!reponse || reponse.error || !reponse.data) return null;
      return reponse.data;
    } catch {
      return null;
    }
  }

  // La carte : le budget de ce qui est enregistré, redemandé à chaque changement.
  useEffect(() => {
    if (!lu) return;
    let actuel = true;
    void demanderBudget(lexique).then((b) => {
      if (actuel) setBudget(b);
    });
    return () => {
      actuel = false;
    };
  }, [lexique, lu]);

  // Le dialogue : le budget du brouillon, après une courte pause de saisie.
  useEffect(() => {
    if (!ouvert) return;
    let actuel = true;
    const minuterie = setTimeout(() => {
      void demanderBudget(brouillon).then((b) => {
        if (actuel) setBudgetDuBrouillon(b);
      });
    }, ATTENTE_BUDGET_MS);
    return () => {
      actuel = false;
      clearTimeout(minuterie);
    };
  }, [brouillon, ouvert]);

  async function enregistrer(suivant: LexiqueMetier, muet = false) {
    setEnregistrement(true);
    setErreur(null);
    try {
      const reponse = await saveLexiqueApiV1OrganizationsLexiquePut({ body: suivant });
      if (reponse.error) {
        // The server's own message: a spelling shared by two terms names both.
        setErreur(echecAffiche(reponse.error, ECHECS.lexiqueEnregistrer));
        return false;
      }
      setLexique(reponse.data ?? suivant);
      if (!muet) notifier.succes({ fr: "Lexique enregistré.", en: "Vocabulary saved." });
      return true;
    } catch {
      setErreur("Failed to save the trade vocabulary");
      return false;
    } finally {
      setEnregistrement(false);
    }
  }

  function ouvrir(ouvre: boolean) {
    if (ouvre) {
      // Une copie profonde : ce qui est modifié dans le dialogue ne touche à
      // rien tant qu'on n'a pas enregistré.
      setBrouillon(JSON.parse(JSON.stringify(lexique)) as LexiqueMetier);
      setBudgetDuBrouillon(budget);
      setRecherche("");
      setErreur(null);
    }
    setOuvert(ouvre);
  }

  async function enregistrerLeBrouillon() {
    const enregistre = await enregistrer(brouillon);
    if (enregistre) setOuvert(false);
  }

  function modifier(rang: number, champs: Partial<TermeLexique>) {
    setBrouillon((actuel) => ({
      ...actuel,
      termes: (actuel.termes ?? []).map((terme, i) =>
        i === rang ? { ...terme, ...champs } : terme,
      ),
    }));
  }

  function ajouter() {
    // Le terme neuf est vide : une recherche en cours le cacherait aussitôt.
    setRecherche("");
    setBrouillon((actuel) => ({
      ...actuel,
      termes: [...(actuel.termes ?? []), { ...TERME_VIDE }],
    }));
  }

  function supprimer(rang: number) {
    setBrouillon((actuel) => ({
      ...actuel,
      termes: (actuel.termes ?? []).filter((_, i) => i !== rang),
    }));
  }

  const termes = lexique.termes ?? [];
  const ecoutes = termes.filter((t) => t.a_ecouter);
  const proposes = termes.filter((t) => t.propose);
  const prononces = termes.filter((t) => t.prononciation).length;

  const termesDuBrouillon = useMemo(() => brouillon.termes ?? [], [brouillon]);
  const chercheSansAccent = sansAccent(recherche.trim());
  const affiches = useMemo(
    () =>
      termesDuBrouillon
        .map((terme, rang) => ({ terme, rang }))
        .filter(({ terme }) => correspond(terme, chercheSansAccent)),
    [termesDuBrouillon, chercheSansAccent],
  );
  const ecoutesDuBrouillon = termesDuBrouillon.filter((t) => t.a_ecouter).length;
  const proposesDuBrouillon = termesDuBrouillon.filter((t) => t.propose).length;

  /** Coche ou décoche ce que la recherche montre, et rien d'autre (décision d'Evan). */
  function cocherLesAffiches(coche: boolean) {
    const rangs = new Set(affiches.map(({ rang }) => rang));
    setBrouillon((actuel) => ({
      ...actuel,
      termes: (actuel.termes ?? []).map((terme, i) =>
        rangs.has(i) ? { ...terme, a_ecouter: coche } : terme,
      ),
    }));
  }

  async function importer(evenement: React.ChangeEvent<HTMLInputElement>) {
    const choisi = evenement.target.files?.[0];
    evenement.target.value = "";
    if (!choisi) return;
    setErreur(null);
    try {
      const contenu = JSON.parse(await choisi.text()) as LexiqueMetier;
      const reponse = await importLexiqueApiV1OrganizationsLexiqueImportPost({ body: contenu });
      if (reponse.error) {
        setErreur(echecAffiche(reponse.error, ECHECS.lexiqueImporter));
        return;
      }
      const resultat = reponse.data;
      notifier.succes({ fr: `${resultat?.ajoutes ?? 0} ajoutés, ${resultat?.deja_presents ?? 0} déjà présents.`, en: `${resultat?.ajoutes ?? 0} added, ${resultat?.deja_presents ?? 0} already there.` });
      await charger();
    } catch {
      setErreur("This file is not a trade vocabulary (expected JSON).");
    }
  }

  function exporter() {
    const aujourdhui = new Date().toISOString().slice(0, 10);
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(
      new Blob([JSON.stringify(lexique, null, 1)], { type: "application/json" }),
    );
    lien.download = `lexique-${aujourdhui}.json`;
    lien.click();
    // Révoquée au tour suivant : révoquée dans la foulée du clic, le
    // téléchargement échoue sur certains navigateurs.
    const adresse = lien.href;
    setTimeout(() => URL.revokeObjectURL(adresse), 0);
  }

  if (chargement) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  // [.mark] K4b : la forme de la maquette (`OngletEcouteSons`) : titre + « ! », recherche, Importer, + Terme à droite, un
  // tableau nu ; un clic sur un terme ouvre sa fenêtre (la route remplace tout le lexique : il part avec le terme changé).
  if (maquette) {
    const termesLus = lexique.termes ?? [];
    const cherche = sansAccent(recherche.trim());
    const vus = termesLus.map((terme, rang) => ({ terme, rang })).filter(({ terme }) => correspond(terme, cherche));
    const courant = typeof terme === "number" ? termesLus[terme] : undefined;
    const nature = (terme: Pick<TermeLexique, "type" | "nature">) => t(NATURES.find((n) => n.id === natureDe(terme))!.nom);
    const oui = t({ en: "yes", fr: "oui" });
    const non = t({ en: "no", fr: "non" });
    const retirer = (rang: number) => {
      const avant = lexique;
      const apres: LexiqueMetier = { ...lexique, termes: termesLus.filter((_, i) => i !== rang) };
      setLexique(apres);
      notifier.annulable(
        { fr: "Terme retiré.", en: "Term removed." },
        {
          restaurer: () => setLexique(avant),
          executer: async () => {
            if (!(await enregistrer(apres, true))) setLexique(avant);
          },
        },
      );
    };
    return (
      <section id="ecoute-lexique" data-testid="lexique-metier">
        <TitreTableau
          titre={t({ en: "Trade vocabulary", fr: "Lexique métier" })}
          info={
            <Info>
              {t({
                en: "The names and words of this business: recognised before the model reads them, listened for by the transcription, and pronounced the way you write them.",
                fr: "Les noms et les mots de l'entreprise : reconnus avant que le modèle ne les lise, écoutés par la transcription, et prononcés comme vous les écrivez.",
              })}
            </Info>
          }
          action={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label={t({ en: "Search the vocabulary", fr: "Chercher dans le lexique" })}
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                  placeholder={t({ en: "A name, a spelling, a category…", fr: "Un nom, une orthographe, une catégorie…" })}
                  className="h-8 w-64 pl-8"
                />
              </div>
              <Button variant="ghost" size="sm" disabled={!lu} onClick={() => setSeuilOuvert(true)}>
                {t({ en: "Common words", fr: "Mots courants" })}
              </Button>
              <Button variant="ghost" size="sm" disabled={!lu} onClick={() => fichier.current?.click()}>
                <Upload className="size-3.5" />
                {t({ en: "Import", fr: "Importer" })}
              </Button>
              <Button variant="ghost" size="sm" onClick={exporter}>
                <Download className="size-3.5" />
                {t({ en: "Export", fr: "Exporter" })}
              </Button>
              <Button variant="outline" size="sm" disabled={!lu} onClick={() => setTerme("nouveau")}>
                <Plus className="size-3.5" />
                {t({ en: "Term", fr: "Terme" })}
              </Button>
              <input ref={fichier} type="file" accept="application/json,.json" className="hidden" aria-label={t({ en: "Import template", fr: "Importer un modèle" })} onChange={importer} />
            </div>
          }
        />
        {erreur && terme === null && (
          <p className="text-xs text-destructive" role="alert">
            {erreur}
          </p>
        )}
        <BudgetDeLaTranscription budget={budget} />
        <div className="mt-10">
        {!lu ? (
          <EtatVide cas="erreur" compact reessayer={() => void charger()} />
        ) : termesLus.length === 0 ? (
          <EtatVide cas="premier" compact icone={BookOpen} titre={t({ en: "No term yet", fr: "Aucun terme pour l'instant" })} />
        ) : vus.length === 0 ? (
          <EtatVide cas="filtre" compact recherche={recherche} effacer={() => setRecherche("")} />
        ) : (
          <Paginee liste={vus}>
            {(page) => (
              <Tableau
                colonnes={[
                  { titre: t({ en: "Term", fr: "Terme" }) },
                  { titre: t({ en: "Other spellings", fr: "Autres orthographes" }) },
                  { titre: t({ en: "Said as", fr: "Se dit" }) },
                  { titre: t({ en: "Category", fr: "Catégorie" }) },
                  { titre: t({ en: "Listened for", fr: "Écouté" }), droite: true },
                  { titre: t({ en: "Offered", fr: "Proposé" }), droite: true },
                ]}
              >
                {page.map(({ terme: l, rang }) => (
                  <Ligne key={rang} onClick={() => setTerme(rang)}>
                    <Cellule principale sous={nature(l)}>
                      {l.terme}
                    </Cellule>
                    <Cellule>{versTexte(l.variantes) || "—"}</Cellule>
                    <Cellule>{l.prononciation || t({ en: "as written", fr: "comme écrit" })}</Cellule>
                    <Cellule>{l.categorie || "—"}</Cellule>
                    <Cellule droite>{l.a_ecouter ? oui : non}</Cellule>
                    <Cellule droite>{l.propose ? oui : non}</Cellule>
                  </Ligne>
                ))}
              </Tableau>
            )}
          </Paginee>
        )}
        </div>
        {terme !== null && (
          <FenetreChamps
            ouverte
            fermer={() => setTerme(null)}
            titre={terme === "nouveau" ? t({ en: "New term", fr: "Nouveau terme" }) : (courant?.terme ?? "")}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            pied={
              courant ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() => {
                    const rang = terme as number;
                    setTerme(null);
                    retirer(rang);
                  }}
                >
                  <Trash2 className="size-3.5" />
                  {t({ en: "Remove", fr: "Retirer" })}
                </Button>
              ) : undefined
            }
            sections={[
              {
                champs: [
                  { id: "terme", t: "texte", l: t({ en: "Term", fr: "Terme" }), v: courant?.terme ?? "", info: t({ en: "Written the way the business writes it.", fr: "Écrit comme l'entreprise l'écrit." }) },
                  {
                    id: "variantes",
                    t: "texte",
                    l: t({ en: "Other spellings", fr: "Autres orthographes" }),
                    v: versTexte(courant?.variantes),
                    info: t({ en: "What the transcription sometimes hears instead, separated by commas: replaced by the term before the model reads it.", fr: "Ce que la transcription entend parfois à la place, séparé par des virgules : remplacé par le terme avant que le modèle ne lise." }),
                  },
                  { id: "prononciation", t: "texte", l: t({ en: "Said as", fr: "Se dit" }), v: courant?.prononciation ?? "", info: t({ en: "Empty: pronounced as written.", fr: "Vide : prononcé comme écrit." }) },
                  { id: "type", t: "choix", l: t({ en: "Kind", fr: "Nature" }), o: NATURES.map((n) => t(n.nom)), v: nature(courant ?? TERME_VIDE) },
                  { id: "categorie", t: "texte", l: t({ en: "Category", fr: "Catégorie" }), v: courant?.categorie ?? "" },
                  { id: "a_ecouter", t: "inter", l: t({ en: "Listen for it", fr: "À écouter" }), v: courant?.a_ecouter ?? TERME_VIDE.a_ecouter, info: t({ en: "Sent to the transcription so that it hears it better.", fr: "Envoyé à la transcription pour qu'elle l'entende mieux." }) },
                  { id: "propose", t: "inter", l: t({ en: "The business offers it", fr: "L'entreprise le propose" }), v: courant?.propose ?? TERME_VIDE.propose, info: t({ en: "The agent may say that the business does or sells it.", fr: "L'agent peut dire que l'entreprise le fait ou le vend." }) },
                ],
              },
            ]}
            verifier={(v) => (String(v.terme ?? "").trim() ? null : { terme: t({ en: "A term cannot be empty.", fr: "Un terme ne peut pas être vide." }) })}
            onValider={(v) => {
              const choisie = NATURES.find((n) => t(n.nom) === v.type)?.id ?? natureDe(courant ?? TERME_VIDE);
              const fait: TermeLexique = {
                terme: String(v.terme).trim(),
                variantes: versVariantes(String(v.variantes ?? "")),
                prononciation: String(v.prononciation ?? "").trim() || null,
                nature: choisie,
                type: choisie === "mot_du_metier" ? "mot" : "nom",
                categorie: String(v.categorie ?? "").trim() || null,
                a_ecouter: v.a_ecouter === true,
                propose: v.propose === true,
              };
              return enregistrer({
                ...lexique,
                termes: terme === "nouveau" ? [...termesLus, fait] : termesLus.map((x, i) => (i === terme ? fait : x)),
              });
            }}
          />
        )}
        {seuilOuvert && (
          <FenetreChamps
            ouverte
            fermer={() => setSeuilOuvert(false)}
            titre={t({ en: "Common words never read as a name", fr: "Mots courants jamais lus comme un nom" })}
            info={t({
              en: `The ${SEUIL_MOTS_COURANTS_DEFAUT.toLocaleString("en")} most frequent French words (the default) are never read as a name of this vocabulary, nor a name made of them. Raise it if everyday words are read as names; lower it if names that sound like words are missed.`,
              fr: `Les ${SEUIL_MOTS_COURANTS_DEFAUT.toLocaleString("fr")} mots français les plus fréquents (le défaut) ne sont jamais lus comme un nom de ce lexique, ni un nom qui en est fait. Montez-le si des mots du quotidien sont lus comme des noms ; baissez-le si des noms qui sonnent comme des mots sont manqués.`,
            })}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            sections={[
              {
                champs: [
                  {
                    id: "seuil",
                    t: "nombre",
                    l: t({ en: "Frequency threshold", fr: "Seuil de fréquence" }),
                    v: String(lexique.seuil_mots_courants ?? SEUIL_MOTS_COURANTS_DEFAUT),
                    min: SEUIL_MOTS_COURANTS_MIN,
                    max: SEUIL_MOTS_COURANTS_MAX,
                  },
                ],
              },
            ]}
            onValider={(v) => enregistrer({ ...lexique, seuil_mots_courants: Number(v.seuil) || SEUIL_MOTS_COURANTS_DEFAUT })}
          />
        )}
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Names and words of this business. Names are recognised and corrected before the model
        reads them; terms ticked &quot;Listen for it&quot; are sent to the transcription; terms
        ticked &quot;The business offers it&quot; are the ones the agent says the business offers;
        &quot;Say it as&quot; changes how the voice pronounces them.
      </p>

      <p className="text-sm">
        <span className="font-medium">{termes.length} terms</span>
        <span className="text-muted-foreground">
          {" · "}
          {ecoutes.length} listened for{" · "}
          {proposes.length} offered{" · "}
          {prononces} pronunciations
        </span>
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={!lu} onClick={() => ouvrir(true)}>
          Open vocabulary
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!lu}
          onClick={() => fichier.current?.click()}
        >
          <Upload className="mr-1 h-4 w-4" />
          Import template
        </Button>
        <input
          ref={fichier}
          type="file"
          accept="application/json,.json"
          className="hidden"
          aria-label="Import template"
          onChange={importer}
        />
        <Button type="button" variant="outline" size="sm" onClick={exporter}>
          <Download className="mr-1 h-4 w-4" />
          Export
        </Button>
      </div>

      {erreur && !ouvert && <p className="text-xs text-destructive">{erreur}</p>}
      {!lu && (
        <p className="text-xs text-destructive">
          Nothing was changed. Saving is disabled until the saved vocabulary can be read.
        </p>
      )}

      <BudgetDeLaTranscription budget={budget} />

      <Dialog open={ouvert} onOpenChange={ouvrir}>
        <DialogContent className="flex max-h-[85vh] max-w-5xl flex-col">
          <DialogHeader>
            <DialogTitle>Trade vocabulary</DialogTitle>
            <DialogDescription>
              &quot;Listen for it&quot;: sent to the transcription. &quot;The business offers
              it&quot;: what the agent says the business offers. Closing without saving changes
              nothing.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label={t({ en: "Search the vocabulary", fr: "Chercher dans le vocabulaire" })}
              placeholder={t({ en: "Search a name, a spelling, a category…", fr: "Chercher un nom, une graphie, une catégorie…" })}
              className="w-full sm:w-72"
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
            />
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {affiches.length} shown · {ecoutesDuBrouillon} of {termesDuBrouillon.length} listened
              for · {proposesDuBrouillon} offered
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={affiches.length === 0}
                onClick={() => cocherLesAffiches(true)}
              >
                <Check className="mr-1 h-4 w-4" />
                Tick the {affiches.length} shown
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={affiches.length === 0}
                onClick={() => cocherLesAffiches(false)}
              >
                <Square className="mr-1 h-4 w-4" />
                Untick the {affiches.length} shown
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={ajouter}>
                <Plus className="mr-1 h-4 w-4" />
                Add term
              </Button>
            </div>
          </div>

          <BudgetDeLaTranscription budget={budgetDuBrouillon} />

          <div className="space-y-1">
            <Label htmlFor="seuil_mots_courants" className="text-xs">
              Common words never read as a name
            </Label>
            <Input
              id="seuil_mots_courants"
              type="number"
              className="w-32"
              min={SEUIL_MOTS_COURANTS_MIN}
              max={SEUIL_MOTS_COURANTS_MAX}
              step={1000}
              value={brouillon.seuil_mots_courants ?? SEUIL_MOTS_COURANTS_DEFAUT}
              onChange={(e) =>
                setBrouillon((actuel) => ({
                  ...actuel,
                  seuil_mots_courants: Number(e.target.value) || SEUIL_MOTS_COURANTS_DEFAUT,
                }))
              }
            />
            <p className="text-xs text-muted-foreground">
              The {SEUIL_MOTS_COURANTS_DEFAUT.toLocaleString("en")} most frequent French words (the default) are
              never read as a name of this vocabulary, nor a name made of them. A rarer word may only be suggested
              to the agent, never taken as sure. Raise it if everyday words are read as names; lower it if names
              that sound like words are missed. From {SEUIL_MOTS_COURANTS_MIN.toLocaleString("en")} to{" "}
              {SEUIL_MOTS_COURANTS_MAX.toLocaleString("en")} (the whole list).
            </p>
          </div>

          {erreur && <p className="text-xs text-destructive">{erreur}</p>}

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {termesDuBrouillon.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No term yet. Import the template of this trade, or add a term.
              </p>
            ) : affiches.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No term matches &quot;{recherche}&quot;.
              </p>
            ) : (
              <div className="space-y-2">
                <div className="hidden gap-2 text-xs font-medium text-muted-foreground md:grid md:grid-cols-[2fr_2fr_2fr_1fr_1fr_auto_auto_auto]">
                  <span>Term</span>
                  <span>Other spellings</span>
                  <span>Say it as</span>
                  <span>Kind</span>
                  <span>Category</span>
                  <span>Listen for it</span>
                  <span>The business offers it</span>
                  <span />
                </div>
                {affiches.map(({ terme, rang }) => (
                  <div
                    key={rang}
                    className="grid gap-2 md:grid-cols-[2fr_2fr_2fr_1fr_1fr_auto_auto_auto] md:items-center"
                  >
                    <Input
                      aria-label={`Term ${rang + 1}`}
                      value={terme.terme}
                      onChange={(e) => modifier(rang, { terme: e.target.value })}
                    />
                    <Input
                      aria-label={`Other spellings ${rang + 1}`}
                      value={versTexte(terme.variantes)}
                      onChange={(e) => modifier(rang, { variantes: versVariantes(e.target.value) })}
                    />
                    <Input
                      aria-label={`Say it as ${rang + 1}`}
                      value={terme.prononciation ?? ""}
                      onChange={(e) => modifier(rang, { prononciation: e.target.value || null })}
                    />
                    <ListeDeroulante
                      aria-label={`Kind ${rang + 1}`}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={terme.type ?? "nom"}
                      onChange={(e) =>
                        modifier(rang, { type: e.target.value as TermeLexique["type"] })
                      }
                    >
                      <option value="nom">Name</option>
                      <option value="mot">Word</option>
                    </ListeDeroulante>
                    <Input
                      aria-label={`Category ${rang + 1}`}
                      value={terme.categorie ?? ""}
                      onChange={(e) => modifier(rang, { categorie: e.target.value || null })}
                    />
                    <div className="flex items-center gap-2">
                      <Label htmlFor={`a_ecouter_${rang}`} className="text-xs md:hidden">
                        Listen for it
                      </Label>
                      <Switch
                        id={`a_ecouter_${rang}`}
                        aria-label={`Listen for it ${rang + 1}`}
                        checked={Boolean(terme.a_ecouter)}
                        onCheckedChange={(coche) => modifier(rang, { a_ecouter: coche })}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Label htmlFor={`propose_${rang}`} className="text-xs md:hidden">
                        The business offers it
                      </Label>
                      <Switch
                        id={`propose_${rang}`}
                        aria-label={`The business offers it ${rang + 1}`}
                        checked={Boolean(terme.propose)}
                        onCheckedChange={(coche) => modifier(rang, { propose: coche })}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${rang + 1}`}
                      onClick={() => supprimer(rang)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={enregistrement}
              onClick={() => ouvrir(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={enregistrement || !lu}
              onClick={() => void enregistrerLeBrouillon()}
            >
              {enregistrement ? "Saving…" : "Save trade vocabulary"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * « 81 / 100 terms (Deepgram) » or « 212 / 500 tokens (Deepgram) », and the
 * ticked terms that would not be sent, exactly as the API computed them for the
 * organization's provider.
 */
function BudgetDeLaTranscription({ budget }: { budget: BudgetLexique | null }) {
  const { t } = useLangue();
  const maquette = useFormeMaquette();
  if (!budget) return null;
  const nonEnvoyes = budget.non_envoyes ?? [];
  const parTermes = budget.plafond_termes !== null && budget.plafond_termes !== undefined;
  const parJetons = budget.plafond_jetons !== null && budget.plafond_jetons !== undefined;
  if (!budget.nom_du_plafond || (!parTermes && !parJetons)) {
    // [.mark] K4b : sur la page de la maquette, rien à dire quand le fournisseur ne déclare aucune limite.
    if (maquette) return null;
    return (
      <p className="text-xs text-muted-foreground" data-testid="budget-lexique">
        {t({ en: "No term is sent to the transcription: its provider", fr: "Aucun terme n'est envoyé à la transcription : son fournisseur" })}
        {budget.fournisseur ? ` (${budget.fournisseur})` : ""} {t({ en: "declares no limit for the list.", fr: "ne déclare aucune limite pour la liste." })}
      </p>
    );
  }
  return (
    <div className="space-y-1 text-xs" data-testid="budget-lexique">
      <p className="text-muted-foreground">
        <span className="font-medium text-foreground">
          {parTermes
            ? `${(budget.envoyes ?? []).length} / ${budget.plafond_termes} ${t({ en: "terms", fr: "termes" })}`
            : `${budget.jetons} / ${budget.plafond_jetons} ${t({ en: "tokens", fr: "jetons" })}`}{" "}
          ({budget.nom_du_plafond})
        </span>{" "}
        {t({ en: "sent to the transcription. Each agent's own Dictionary is sent first and takes from the same limit.", fr: "envoyés à la transcription. Le dictionnaire propre à chaque agent part en premier et prend sur la même limite." })}
      </p>
      {nonEnvoyes.length > 0 && (
        <p className="text-destructive">
          {t({ en: `Not sent (${nonEnvoyes.length}): `, fr: `Non envoyés (${nonEnvoyes.length}) : ` })}{nonEnvoyes.join(", ")}
        </p>
      )}
    </div>
  );
}
