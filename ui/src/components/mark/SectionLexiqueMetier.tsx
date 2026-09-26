"use client";

import { Check, Download, Plus, Square, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  budgetLexiqueApiV1OrganizationsLexiqueBudgetPost,
  getLexiqueApiV1OrganizationsLexiqueGet,
  importLexiqueApiV1OrganizationsLexiqueImportPost,
  saveLexiqueApiV1OrganizationsLexiquePut,
} from "@/client/sdk.gen";
import type { BudgetLexique, LexiqueMetier, TermeLexique } from "@/client/types.gen";
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
import { detailFromError } from "@/lib/apiError";
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
 * « 212 / 450 tokens (Deepgram) » with the ticked terms left out, is asked of
 * the API for the organization's provider: ⛔ the screen never counts on its
 * own, and no ceiling is written here.
 */

/** Wait this long after the last change of the draft before asking the budget again. */
const ATTENTE_BUDGET_MS = 300;

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
          detailFromError(reponse.error, "Failed to load the trade vocabulary"),
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

  async function enregistrer(suivant: LexiqueMetier) {
    setEnregistrement(true);
    setErreur(null);
    try {
      const reponse = await saveLexiqueApiV1OrganizationsLexiquePut({ body: suivant });
      if (reponse.error) {
        // The server's own message: a spelling shared by two terms names both.
        setErreur(detailFromError(reponse.error, "Failed to save the trade vocabulary"));
        return false;
      }
      setLexique(reponse.data ?? suivant);
      toast.success("Trade vocabulary saved");
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
        setErreur(detailFromError(reponse.error, "Failed to import the template"));
        return;
      }
      const resultat = reponse.data;
      toast.success(
        `${resultat?.ajoutes ?? 0} added, ${resultat?.deja_presents ?? 0} already there`,
      );
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
              aria-label="Search the vocabulary"
              placeholder="Search a name, a spelling, a category…"
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
                    <select
                      aria-label={`Kind ${rang + 1}`}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={terme.type ?? "nom"}
                      onChange={(e) =>
                        modifier(rang, { type: e.target.value as TermeLexique["type"] })
                      }
                    >
                      <option value="nom">Name</option>
                      <option value="mot">Word</option>
                    </select>
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
 * « 212 / 450 tokens (Deepgram) » and the ticked terms that would not be sent,
 * exactly as the API computed them for the organization's provider.
 */
function BudgetDeLaTranscription({ budget }: { budget: BudgetLexique | null }) {
  if (!budget) return null;
  const nonEnvoyes = budget.non_envoyes ?? [];
  if (budget.plafond_jetons === null || budget.plafond_jetons === undefined) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="budget-lexique">
        No term is sent to the transcription: its provider
        {budget.fournisseur ? ` (${budget.fournisseur})` : ""} declares no limit for the list.
      </p>
    );
  }
  return (
    <div className="space-y-1 text-xs" data-testid="budget-lexique">
      <p className="text-muted-foreground">
        <span className="font-medium text-foreground">
          {budget.jetons} / {budget.plafond_jetons} tokens ({budget.nom_du_plafond})
        </span>{" "}
        sent to the transcription. Each agent&apos;s own Dictionary is sent first and takes from
        the same limit.
      </p>
      {nonEnvoyes.length > 0 && (
        <p className="text-destructive">
          Not sent ({nonEnvoyes.length}): {nonEnvoyes.join(", ")}
        </p>
      )}
    </div>
  );
}
