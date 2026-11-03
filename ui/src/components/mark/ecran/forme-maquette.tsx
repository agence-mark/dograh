"use client";

/**
 * [.mark] K4b : la FORME de la maquette pour les pages « Entreprise » et « Base et automatisations ». Les thèmes
 * d'organisation gardent leur forme d'avant (réglages tous visibles, tests d'inventaire) tant que ce contexte n'est
 * pas posé ; les deux pages le posent, et alors :
 *  - une explication n'est jamais une phrase visible : elle passe dans un « ! » (`ChampReglage`, `Intertitre`) ;
 *  - un intertitre devient le titre d'un tableau (titre + « ! », trait, lignes séparées) ;
 *  - un bloc long se lit en lignes, « Modifier » ouvre sa fenêtre (`BlocLu`).
 */
import { createContext, type ReactNode, useContext } from "react";

const Contexte = createContext(false);

export const FormeMaquette = ({ children }: { children: ReactNode }) => <Contexte.Provider value>{children}</Contexte.Provider>;

export const useFormeMaquette = () => useContext(Contexte);
