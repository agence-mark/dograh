import SpinLoader from "@/components/SpinLoader";

/**
 * [.mark] L (fluidité) : l'éditeur d'un agent (graphe, panneaux) est la page la plus lourde. Cette limite de chargement
 * est ce que Next précharge avec le lien de la liste des agents : le clic affiche l'attente tout de suite, sans écran
 * blanc, pendant que le code de l'éditeur arrive.
 */
export default function Loading() {
  return <SpinLoader />;
}
