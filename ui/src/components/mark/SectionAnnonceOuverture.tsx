"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet,
  saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut,
} from "@/client/sdk.gen";
import type { ReglagesAnnonceOuverture } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

/**
 * [.mark] What the agents say at pick-up when the business is closed, and the
 * state forced by hand (chantier reglages-annonce-ouverture, 18/09/2026).
 *
 * Why this card exists: the two sentences were written IN THE CODE. A setting
 * that changes what a caller hears is seen and changed on screen.
 *
 * ⚠️ These settings belong to the ORGANIZATION: they are true for the whole
 * company. The opening HOURS stay on each agent, because they describe a place.
 * Which is why a forced state closes every agent of the organization, and the
 * card says so: to close ONE site, the hours of that agent take a dated
 * exception (« 24/12/2026 : fermé »), which the format already allows.
 */

export const ETAT_CALCULE = "";

/** The states that can be forced, in the order they are offered. */
const ETATS: Array<{ valeur: string; libelle: string }> = [
  { valeur: "FERME", libelle: "Closed" },
  { valeur: "PAUSE", libelle: "On a break" },
  { valeur: "OUVERT", libelle: "Open" },
  { valeur: "SUR_RENDEZ_VOUS", libelle: "By appointment only" },
];

/** What the preview puts in « {reouverture} » -- an EXAMPLE, the server words the real one. */
const REOUVERTURE_EXEMPLE = "demain à 10 heures";

const VIDE: ReglagesAnnonceOuverture = {
  annonce_fermeture: "",
  annonce_pause: "",
  etat_force: null,
  etat_force_jusqu_a: null,
};

/**
 * Put a sentence into the words the greeting will say.
 *
 * ⚠️ The same two rules as `rendre_annonce` on the server: what is in brackets
 * is said only when the reopening is known, and « {reouverture} » is replaced
 * by it. This copy is for the PREVIEW only -- what a caller hears is always
 * built by the server.
 */
export function rendreAnnonce(modele: string, reouverture: string): string {
  const texte = (modele ?? "").trim();
  if (!texte) return "";
  let sortie: string;
  if (reouverture) {
    sortie = texte.replace(/[[\]]/g, "");
  } else {
    // An unclosed « [ » is optional to the end, exactly like on the server.
    let profondeur = 0;
    sortie = "";
    for (const caractere of texte) {
      if (caractere === "[") profondeur += 1;
      else if (caractere === "]") profondeur = Math.max(0, profondeur - 1);
      else if (profondeur === 0) sortie += caractere;
    }
  }
  return sortie.split("{reouverture}").join(reouverture).replace(/\s+/g, " ").trim();
}

/** « 2026-12-24T10:00:00 » -> « 2026-12-24T10:00 », what the date field reads. */
function versChamp(valeur: string | null | undefined): string {
  return valeur ? valeur.slice(0, 16) : "";
}

function Apercu({ modele, titre }: { modele: string; titre: string }) {
  const avec = rendreAnnonce(modele, REOUVERTURE_EXEMPLE);
  const sans = rendreAnnonce(modele, "");
  return (
    <div className="rounded-md border bg-muted/40 p-3 text-xs">
      <p className="font-medium">{titre}</p>
      <p className="mt-1 text-muted-foreground">
        Reopening known (example):{" "}
        <span className="text-foreground">{avec || "nothing is announced"}</span>
      </p>
      <p className="text-muted-foreground">
        Reopening unknown:{" "}
        <span className="text-foreground">{sans || "nothing is announced"}</span>
      </p>
    </div>
  );
}

export function SectionAnnonceOuverture() {
  const [reglages, setReglages] = useState<ReglagesAnnonceOuverture>(VIDE);
  const [chargement, setChargement] = useState(true);
  const [enregistrement, setEnregistrement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [lu, setLu] = useState(false);
  const { user, loading: authLoading } = useAuth();
  const dejaLu = useRef(false);

  // ⛔ Convention of the repository: the token is attached only once auth is
  // loaded. Reading before that sends an unauthenticated request that fails in
  // silence, and the screen would show the defaults.
  useEffect(() => {
    if (authLoading || !user || dejaLu.current) return;
    dejaLu.current = true;
    void charger();
  }, [authLoading, user]);

  async function charger() {
    setChargement(true);
    try {
      const reponse = await getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet();
      if (reponse.error || !reponse.data) {
        // ⛔ Saving REPLACES the settings whole: until what is saved has been
        // read, nothing may overwrite it.
        setLu(false);
        setErreur(detailFromError(reponse.error, "Failed to load the announcement settings"));
        return;
      }
      setReglages(reponse.data);
      setLu(true);
      setErreur(null);
    } catch {
      setLu(false);
      setErreur("Failed to load the announcement settings");
    } finally {
      setChargement(false);
    }
  }

  async function enregistrer() {
    setEnregistrement(true);
    setErreur(null);
    try {
      const reponse = await saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut({
        body: reglages,
      });
      if (reponse.error) {
        // The server's own message: an unclosed bracket, a placeholder that
        // does not exist, a date without a forced state.
        setErreur(detailFromError(reponse.error, "Failed to save the announcement settings"));
        return;
      }
      setReglages(reponse.data ?? reglages);
      toast.success("Announcement settings saved");
    } catch {
      setErreur("Failed to save the announcement settings");
    } finally {
      setEnregistrement(false);
    }
  }

  function modifier(champs: Partial<ReglagesAnnonceOuverture>) {
    setReglages((actuel) => ({ ...actuel, ...champs }));
    setErreur(null);
  }

  const force = reglages.etat_force ?? null;
  const parle = force === "FERME" || force === "PAUSE";

  if (chargement) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Said at pick-up, before the greeting, when the business is not reachable. An open
        business says nothing extra.{" "}
        <code className="rounded bg-muted px-1 text-xs">{"{reouverture}"}</code> is the
        reopening the agent announces, and what is inside{" "}
        <code className="rounded bg-muted px-1 text-xs">[ ]</code> is said only when that
        reopening is known. An empty sentence announces nothing.
      </p>

      <div className="space-y-2">
        <Label htmlFor="annonce_fermeture" className="text-xs">
          When the business is closed
        </Label>
        <Textarea
          id="annonce_fermeture"
          rows={2}
          maxLength={300}
          value={reglages.annonce_fermeture ?? ""}
          onChange={(e) => modifier({ annonce_fermeture: e.target.value })}
        />
        <Apercu modele={reglages.annonce_fermeture ?? ""} titre="Closed, as it will be said" />
      </div>

      <div className="space-y-2">
        <Label htmlFor="annonce_pause" className="text-xs">
          When the business is on a break
        </Label>
        <p className="text-xs text-muted-foreground">
          A break means already open today and reopening today, not lunch.
        </p>
        <Textarea
          id="annonce_pause"
          rows={2}
          maxLength={300}
          value={reglages.annonce_pause ?? ""}
          onChange={(e) => modifier({ annonce_pause: e.target.value })}
        />
        <Apercu modele={reglages.annonce_pause ?? ""} titre="On a break, as it will be said" />
      </div>

      <div className="space-y-2 border-t pt-4">
        <Label htmlFor="etat_force" className="text-xs">
          State of the business
        </Label>
        <select
          id="etat_force"
          aria-label="State of the business"
          className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={force ?? ETAT_CALCULE}
          onChange={(e) =>
            modifier(
              e.target.value === ETAT_CALCULE
                ? // Back to « computed »: the end date goes with it. It means
                  // nothing on its own, and the server refuses it alone.
                  { etat_force: null, etat_force_jusqu_a: null }
                : { etat_force: e.target.value as ReglagesAnnonceOuverture["etat_force"] },
            )
          }
        >
          <option value={ETAT_CALCULE}>Computed from each agent&apos;s opening hours</option>
          {ETATS.map((etat) => (
            <option key={etat.valeur} value={etat.valeur}>
              Forced: {etat.libelle}
            </option>
          ))}
        </select>

        {force !== null && (
          <>
            <Label htmlFor="etat_force_jusqu_a" className="text-xs">
              Until (Paris time)
            </Label>
            <Input
              id="etat_force_jusqu_a"
              type="datetime-local"
              value={versChamp(reglages.etat_force_jusqu_a)}
              onChange={(e) => modifier({ etat_force_jusqu_a: e.target.value || null })}
            />
            <p className="text-xs text-muted-foreground">
              {parle
                ? "This moment is announced as the reopening, and it lifts the forced state by itself: after it the agents go back to their opening hours, with nobody doing anything."
                : "This moment lifts the forced state by itself: after it the agents go back to their opening hours."}{" "}
              Left empty, the forced state holds until someone comes back here
              {parle ? ", and no reopening is announced." : "."}
            </p>
            <p className="text-xs text-destructive">
              A forced state applies to EVERY agent of this organization. To close one site
              only, add a dated exception in that agent&apos;s opening hours (
              <code>24/12/2026 : fermé</code>).
            </p>
          </>
        )}
      </div>

      {erreur && (
        <p role="alert" className="text-xs text-destructive">
          {erreur}
        </p>
      )}
      {!lu && (
        <p className="text-xs text-destructive">
          Nothing was changed. Saving is disabled until the saved settings can be read.
        </p>
      )}

      <Button type="button" disabled={enregistrement || !lu} onClick={() => void enregistrer()}>
        {enregistrement ? "Saving…" : "Save announcement settings"}
      </Button>
    </div>
  );
}
