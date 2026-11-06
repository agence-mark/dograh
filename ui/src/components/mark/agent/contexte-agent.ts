"use client";

import { createContext, useContext } from "react";

/** [.mark] T6 : le nom de l'agent dont l'onglet est ouvert, pour que la page d'un onglet nomme l'agent (« Retour à ⟦agent⟧ »). */
export const ContexteNomAgent = createContext<string>("");
export const useNomAgent = () => useContext(ContexteNomAgent);
