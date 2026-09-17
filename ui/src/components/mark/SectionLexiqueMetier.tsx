"use client";

import { Download, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getLexiqueApiV1OrganizationsLexiqueGet,
  importLexiqueApiV1OrganizationsLexiqueImportPost,
  saveLexiqueApiV1OrganizationsLexiquePut,
} from "@/client/sdk.gen";
import type { LexiqueMetier, TermeLexique } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
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
 */

/** The budget of the list sent to the transcription (T11, raised on 2026-09-17). */
const MAX_TERMES_ECOUTES = 120;
const MAX_CARACTERES_ECOUTES = 1600;

const TERME_VIDE: TermeLexique = {
  terme: "",
  variantes: [],
  prononciation: null,
  type: "nom",
  categorie: null,
  a_ecouter: true,
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

export function SectionLexiqueMetier() {
  const [lexique, setLexique] = useState<LexiqueMetier>({ termes: [] });
  const [chargement, setChargement] = useState(true);
  const [enregistrement, setEnregistrement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
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
      if (reponse.data) {
        setLexique(reponse.data);
      }
    } catch {
      toast.error("Failed to load the trade vocabulary");
    } finally {
      setChargement(false);
    }
  }

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

  function modifier(rang: number, champs: Partial<TermeLexique>) {
    setLexique((actuel) => ({
      ...actuel,
      termes: (actuel.termes ?? []).map((terme, i) =>
        i === rang ? { ...terme, ...champs } : terme,
      ),
    }));
  }

  function ajouter() {
    setLexique((actuel) => ({ ...actuel, termes: [...(actuel.termes ?? []), { ...TERME_VIDE }] }));
  }

  function supprimer(rang: number) {
    setLexique((actuel) => ({
      ...actuel,
      termes: (actuel.termes ?? []).filter((_, i) => i !== rang),
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
    URL.revokeObjectURL(lien.href);
  }

  const termes = lexique.termes ?? [];
  const ecoutes = termes.filter((t) => t.a_ecouter);
  const caracteres = ecoutes.reduce((total, t) => total + t.terme.length, 0);

  if (chargement) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Names and words of this business. Names are recognised and corrected before the model
        reads them; ticked terms are listened for by the transcription; &quot;Say it as&quot;
        changes how the voice pronounces them.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={ajouter}>
          <Plus className="mr-1 h-4 w-4" />
          Add term
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
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
        <Button
          type="button"
          size="sm"
          disabled={enregistrement}
          onClick={() => void enregistrer(lexique)}
        >
          {/* Named like the other cards of the page: a bare "Save" would be one
              of several on the same screen, for Evan and for a test alike. */}
          {enregistrement ? "Saving…" : "Save trade vocabulary"}
        </Button>
      </div>

      {erreur && <p className="text-xs text-destructive">{erreur}</p>}

      <p className="text-xs text-muted-foreground">
        {ecoutes.length} terms listened for (the agent&apos;s Dictionary comes first;{" "}
        {MAX_TERMES_ECOUTES} terms / {MAX_CARACTERES_ECOUTES} characters in total), {caracteres}{" "}
        characters.
      </p>

      {termes.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No term yet. Import the template of this trade, or add a term.
        </p>
      ) : (
        <div className="space-y-2">
          <div className="hidden gap-2 text-xs font-medium text-muted-foreground md:grid md:grid-cols-[2fr_2fr_2fr_1fr_1fr_auto_auto]">
            <span>Term</span>
            <span>Other spellings</span>
            <span>Say it as</span>
            <span>Kind</span>
            <span>Category</span>
            <span>Listen for</span>
            <span />
          </div>
          {termes.map((terme, rang) => (
            <div
              key={rang}
              className="grid gap-2 md:grid-cols-[2fr_2fr_2fr_1fr_1fr_auto_auto] md:items-center"
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
                onChange={(e) =>
                  modifier(rang, { prononciation: e.target.value || null })
                }
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
                  Listen for
                </Label>
                <Switch
                  id={`a_ecouter_${rang}`}
                  aria-label={`Listen for ${rang + 1}`}
                  checked={Boolean(terme.a_ecouter)}
                  onCheckedChange={(coche) => modifier(rang, { a_ecouter: coche })}
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
  );
}
