"use client"

import * as DialogPrimitive from "@radix-ui/react-dialog"
import { ArrowLeft, XIcon } from "lucide-react"
import * as React from "react"

import { useLangue } from "@/components/mark/langue/langue"
import { GardeDeSaisie } from "@/components/mark/agent/brouillon-local"
import { FenetreParente, sansTaille, tailleDe } from "@/components/mark/studio/fenetre-parente"
import { largeurAnnoncee, usePanneau } from "@/components/mark/studio/panneau-droit"
import { cn } from "@/lib/utils"

/**
 * [.mark] Partie 3, sous-lot 19 : toute fenêtre s'ouvre dans le panneau de droite du cadre (`panneau-droit.tsx`), sauf
 * celles qui portent `centree` (supprimer, publier, création, configurateurs : liste écrite dans `07-fenetres-panneau-ou-centrees.md`
 * et gardée par `inventaire-fenetres.test.ts`). Hors du cadre commun, la fenêtre reste centrée. `nouvelOnglet` : un objet à
 * part entière ouvert depuis une fenêtre prend son propre onglet au lieu de s'empiler avec une flèche retour.
 */
const ModeFenetre = React.createContext<{ enPanneau: boolean; nouvelOnglet: boolean }>({ enPanneau: false, nouvelOnglet: false })
const ContexteOnglet = React.createContext<{ racine: string; titre: () => string } | null>(null)

function Dialog({
  centree = false,
  nouvelOnglet = false,
  modal,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Root> & { centree?: boolean; nouvelOnglet?: boolean }) {
  const panneau = usePanneau()
  const enPanneau = !!panneau && !centree
  const mode = React.useMemo(() => ({ enPanneau, nouvelOnglet }), [enPanneau, nouvelOnglet])
  return (
    <ModeFenetre.Provider value={mode}>
      <DialogPrimitive.Root data-slot="dialog" modal={enPanneau ? false : modal} {...props} />
    </ModeFenetre.Provider>
  )
}

function DialogTrigger({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/50",
        className
      )}
      {...props}
    />
  )
}

function DialogContent(props: React.ComponentProps<typeof DialogPrimitive.Content>) {
  const { enPanneau } = React.useContext(ModeFenetre)
  return enPanneau ? <ContenuPanneau {...props} /> : <ContenuCentre {...props} />
}

/** La fenêtre dans le panneau de droite : un onglet (ou un détail empilé avec flèche retour), jamais de voile ni de verrou de page. */
function ContenuPanneau({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  const panneau = usePanneau()!
  const { nouvelOnglet } = React.useContext(ModeFenetre)
  const parente = React.useContext(FenetreParente)
  const ctxOnglet = React.useContext(ContexteOnglet)
  const id = React.useId()
  const empile = !!parente && !nouvelOnglet && !!ctxOnglet
  const racine = empile ? ctxOnglet!.racine : id
  const noeud = React.useRef<HTMLDivElement | null>(null)
  const fermeture = React.useRef<HTMLButtonElement | null>(null)
  const fermer = React.useCallback(() => fermeture.current?.click(), [])
  // Le « ! » d'une info-bulle posée dans le titre n'est pas une lettre du titre : il ne passe ni à l'onglet ni au lien retour.
  const titreDe = React.useCallback(() => {
    const titre = noeud.current?.querySelector('[data-slot="dialog-title"]')
    if (!titre) return ""
    const copie = titre.cloneNode(true) as Element
    copie.querySelectorAll("[data-marque-info]").forEach((x) => x.remove())
    return copie.textContent?.trim() ?? ""
  }, [])
  const largeur = largeurAnnoncee(className)
  // Le titre de l'onglet suit celui de la fenêtre (un nom chargé après coup, un onglet de la fenêtre qui change).
  const observateur = React.useRef<MutationObserver | null>(null)
  const poserNoeud = React.useCallback(
    (el: HTMLDivElement | null) => {
      noeud.current = el
      observateur.current?.disconnect()
      if (!el) return
      const suivre = () => {
        if (!empile) panneau.majTitre(id, titreDe())
      }
      suivre()
      if (typeof MutationObserver !== "undefined") {
        observateur.current = new MutationObserver(suivre)
        observateur.current.observe(el, { childList: true, subtree: true, characterData: true })
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [empile, id, panneau.majTitre, titreDe]
  )
  const detailsDeLOnglet = panneau.details.filter((d) => d.racine === racine)
  const couvert = empile ? detailsDeLOnglet[detailsDeLOnglet.length - 1]?.id !== id : detailsDeLOnglet.length > 0
  const visible = panneau.actif === racine
  const taille = parente ? parente.classe : tailleDe(className) || "sm:max-w-lg"
  const contexteOnglet = React.useMemo(() => ({ racine, titre: titreDe }), [racine, titreDe])
  if (!panneau.corps) return null
  return (
    <DialogPortal data-slot="dialog-portal" container={panneau.corps}>
      <DialogPrimitive.Content
        ref={poserNoeud}
        onCloseAutoFocus={() => {
          document.body.style.pointerEvents = ""
        }}
        // Le panneau laisse la page vivante : ni clic dehors ni perte de focus ne ferme l'onglet.
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => {
          e.preventDefault()
          panneau.echap()
        }}
        data-slot="dialog-content"
        data-panneau=""
        data-imbriquee={empile ? "" : undefined}
        style={visible ? undefined : { display: "none" }}
        {...(couvert ? { inert: true } : {})}
        className={cn(
          "bg-card text-card-foreground grid gap-4 p-6",
          !/(^|\s)overflow-/.test(className ?? "") && "overflow-y-auto",
          sansTaille(className),
          empile ? "absolute inset-0 z-10" : "h-full"
        )}
        {...props}
      >
        <GardeDeSaisie />
        <InscriptionPanneau id={id} racine={racine} empile={empile} fermer={fermer} titreDe={titreDe} largeur={largeur} />
        <FenetreParente.Provider value={{ classe: taille }}>
          <ContexteOnglet.Provider value={contexteOnglet}>
            {empile && <FlecheRetourPanneau titreParent={ctxOnglet!.titre()} />}
            {children}
          </ContexteOnglet.Provider>
        </FenetreParente.Provider>
        <DialogPrimitive.Close ref={fermeture} hidden aria-hidden tabIndex={-1} data-fermeture-panneau="" />
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

/** Monté dans la fenêtre ouverte seulement : l'onglet existe tant que la fenêtre est ouverte. */
function InscriptionPanneau({ id, racine, empile, fermer, titreDe, largeur }: { id: string; racine: string; empile: boolean; fermer: () => void; titreDe: () => string; largeur?: number }) {
  const { inscrire, retirer, inscrireDetail, retirerDetail } = usePanneau()!
  React.useLayoutEffect(() => {
    if (empile) {
      inscrireDetail({ id, racine, fermer })
      return () => retirerDetail(id)
    }
    inscrire({ id, titre: titreDe(), apercu: true, fermer, largeur })
    return () => retirer(id)
  }, [empile, id, racine, fermer, titreDe, largeur, inscrire, retirer, inscrireDetail, retirerDetail])
  return null
}

/** La flèche retour d'un détail empilé (même classes que `FlecheRetour`) : au nom du parent, elle remonte d'un niveau. */
function FlecheRetourPanneau({ titreParent }: { titreParent: string }) {
  const { t } = useLangue()
  const [nom] = React.useState(titreParent)
  return (
    <DialogPrimitive.Close
      data-slot="dialog-close"
      data-fleche-retour=""
      className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 justify-self-start rounded-sm text-sm text-muted-foreground hover:font-semibold hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <ArrowLeft className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{nom || t({ en: "Back", fr: "Retour" })}</span>
    </DialogPrimitive.Close>
  )
}

function ContenuCentre({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  // [.mark] E71 : ouverte depuis une autre fenêtre, elle prend sa taille exacte et une flèche retour remplace la croix.
  const parente = React.useContext(FenetreParente)
  const { t } = useLangue()
  const taille = parente ? parente.classe : tailleDe(className) || "sm:max-w-lg"
  return (
    <DialogPortal data-slot="dialog-portal">
      <DialogOverlay />
      <DialogPrimitive.Content
        onOpenAutoFocus={e => e.preventDefault()}
        onCloseAutoFocus={() => {
          document.body.style.pointerEvents = "";
        }}
        onPointerDownOutside={(e) => {
          // Prevent the Dialog from closing when the user clicks inside a
          // portaled Radix Popover/DropdownMenu rendered on top of this Dialog.
          const target = e.target as HTMLElement;
          if (target.closest('[data-radix-popper-content-wrapper]')) {
            e.preventDefault();
          }
        }}
        onInteractOutside={(e) => {
          const target = e.target as HTMLElement;
          if (target.closest('[data-radix-popper-content-wrapper]')) {
            e.preventDefault();
          }
        }}
        data-slot="dialog-content"
        data-centree=""
        data-imbriquee={parente ? "" : undefined}
        className={cn(
          "bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-xl border-0 p-6 shadow-2xl ring-1 ring-black/5 duration-200 dark:ring-white/10 sm:max-w-lg",
          className,
          parente && parente.classe
        )}
        {...props}
      >
        <GardeDeSaisie />
        <FenetreParente.Provider value={{ classe: taille }}>{children}</FenetreParente.Provider>
        {parente ? (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            aria-label={t({ en: "Back", fr: "Retour" })}
            title={t({ en: "Back", fr: "Retour" })}
            className="absolute top-[22px] left-5 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-hidden"
          >
            <ArrowLeft className="size-4" />
          </DialogPrimitive.Close>
        ) : (
        <DialogPrimitive.Close className="ring-offset-background focus:ring-ring data-[state=open]:bg-accent data-[state=open]:text-muted-foreground absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4">
          <XIcon />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    />
  )
}

function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("text-lg leading-none font-semibold", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-muted-foreground text-sm", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
