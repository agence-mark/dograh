/**
 * [.mark] V2b (E51) : la configuration de modèles de l'organisation, brique par brique.
 *
 * Questions de ce fichier :
 *
 *     Une brique réglée seule recompose-t-elle la configuration ENTIÈRE sans toucher aux autres ? Une brique exigée
 *     et absente (ou sans clé) refuse-t-elle l'enregistrement au lieu d'envoyer une moitié de configuration ? La
 *     fenêtre montre-t-elle, avec la brique ouverte, celles qu'il manque ? Une carte lit-elle une clé référencée
 *     sans jamais en montrer la valeur ?
 */
import { describe, expect, it } from "vitest";

import type { ServiceConfigurationDefaults } from "@/components/ServiceConfigurationForm";

import {
    blocEnregistre,
    briquesManquantes,
    ConfigurationIncomplete,
    construireCorps,
    existantDuMode,
    modeActifEnregistre,
    modeEnregistre,
    segmentsDeLaFenetre,
    vueDeLaBrique,
} from "./configuration-organisation";

// Tous les fournisseurs de l'essai exigent une clé.
const schema = { required: ["api_key"], properties: {} };
const DEFAUTS = {
    llm: { mistral: schema },
    tts: { cartesia: schema },
    stt: { soniox: schema },
    embeddings: { openai: schema },
    realtime: { openai_realtime: schema },
    default_providers: {},
} as unknown as ServiceConfigurationDefaults;

const CHAINE = {
    version: 2,
    mode: "byok",
    byok: {
        mode: "pipeline",
        pipeline: {
            llm: { provider: "mistral", api_key: "mark-cle:cle-m", model: "mistral-small-2603" },
            tts: { provider: "cartesia", api_key: "mark-cle:cle-c", model: "sonic-3.6" },
            stt: { provider: "soniox", api_key: "****1234", model: "stt-rt-v3" },
            embeddings: { provider: "openai", api_key: "mark-cle:cle-o", model: "text-embedding-3-small" },
        },
    },
};
const TEMPS_REEL = {
    version: 2,
    mode: "byok",
    byok: {
        mode: "realtime",
        realtime: {
            realtime: { provider: "openai_realtime", api_key: "mark-cle:cle-o", model: "gpt-realtime" },
            llm: { provider: "mistral", api_key: "mark-cle:cle-m", model: "mistral-small-2603" },
        },
    },
};

describe("lire ce que l'organisation a réglé", () => {
    it("le mode enregistré est celui de la configuration", () => {
        expect(modeEnregistre(CHAINE, {})).toBe("chaine");
        expect(modeEnregistre(TEMPS_REEL, {})).toBe("temps-reel");
    });

    it("une organisation sans configuration enregistrée est en chaîne, sans rien de réglé", () => {
        const vide = existantDuMode(null, {}, "chaine");
        expect(modeEnregistre(null, {})).toBe("chaine");
        expect(vueDeLaBrique(vide, "llm")).toBeNull();
        expect(briquesManquantes("chaine", vide, DEFAUTS)).toEqual(["stt", "llm", "tts"]);
    });

    it("le cerveau réglé dans un mode sert aussi à l'autre ; la voix et la transcription, non", () => {
        const enTempsReel = existantDuMode(CHAINE, {}, "temps-reel");
        expect(vueDeLaBrique(enTempsReel, "llm")?.fournisseur).toBe("mistral");
        expect(vueDeLaBrique(enTempsReel, "realtime")).toBeNull();
        expect(briquesManquantes("temps-reel", enTempsReel, DEFAUTS)).toEqual(["realtime"]);
        expect(briquesManquantes("chaine", existantDuMode(TEMPS_REEL, {}, "chaine"), DEFAUTS)).toEqual(["stt", "tts"]);
    });

    it("une carte lit le modèle et dit la clé de la bibliothèque par son identifiant, jamais sa valeur", () => {
        const existant = existantDuMode(CHAINE, {}, "chaine");
        expect(vueDeLaBrique(existant, "llm")).toEqual({ fournisseur: "mistral", modele: "mistral-small-2603", cle: "cle-m" });
        // Une clé tapée à la main arrive masquée : la carte dit « saisie », pas les derniers caractères.
        expect(vueDeLaBrique(existant, "stt")).toEqual({ fournisseur: "soniox", modele: "stt-rt-v3", cle: "saisie" });
        expect(JSON.stringify(vueDeLaBrique(existant, "stt"))).not.toContain("1234");
    });
});

describe("enregistrer une brique", () => {
    it("recompose la configuration entière : la brique du formulaire change, les autres restent", () => {
        const existant = existantDuMode(CHAINE, {}, "chaine");
        const corps = construireCorps(
            "chaine",
            existant,
            { llm: { provider: "mistral", api_key: "mark-cle:cle-m", model: "mistral-medium-2508" } },
            ["llm"],
            DEFAUTS,
        );
        const chaine = corps.byok!.pipeline!;
        expect(corps.byok!.mode).toBe("pipeline");
        expect((chaine.llm as { model: string }).model).toBe("mistral-medium-2508");
        expect((chaine.tts as { provider: string }).provider).toBe("cartesia");
        expect((chaine.stt as { api_key: string }).api_key).toBe("****1234");
        expect((chaine.embeddings as { provider: string }).provider).toBe("openai");
    });

    it("une brique que la fenêtre ne montre pas n'écrase pas ce qui est réglé (le formulaire rend tout)", () => {
        const existant = existantDuMode(CHAINE, {}, "chaine");
        const corps = construireCorps(
            "chaine",
            existant,
            {
                llm: { provider: "mistral", api_key: "mark-cle:cle-m", model: "m" },
                tts: { provider: "cartesia", api_key: "", model: "défaut-du-formulaire" },
            },
            ["llm"],
            DEFAUTS,
        );
        expect((corps.byok!.pipeline!.tts as { model: string }).model).toBe("sonic-3.6");
    });

    it("refuse une brique exigée sans clé au lieu d'envoyer une moitié de configuration", () => {
        const vide = existantDuMode(null, {}, "chaine");
        const essai = () =>
            construireCorps("chaine", vide, { llm: { provider: "mistral", api_key: "mark-cle:cle-m" } }, ["llm"], DEFAUTS);
        expect(essai).toThrow(ConfigurationIncomplete);
        try {
            essai();
        } catch (e) {
            expect((e as ConfigurationIncomplete).service).toBe("tts");
        }
    });

    it("refuse aussi une brique dont le fournisseur est choisi mais la clé vide", () => {
        const existant = existantDuMode(CHAINE, {}, "chaine");
        expect(() =>
            construireCorps("chaine", existant, { llm: { provider: "mistral", api_key: "" } }, ["llm"], DEFAUTS),
        ).toThrow(ConfigurationIncomplete);
    });

    it("à une organisation vide, la fenêtre d'une brique montre aussi les briques à régler avec elle", () => {
        const vide = existantDuMode(null, {}, "chaine");
        expect(segmentsDeLaFenetre("llm", "chaine", vide, DEFAUTS)).toEqual(["llm", "stt", "tts"]);
        const corps = construireCorps(
            "chaine",
            vide,
            {
                llm: { provider: "mistral", api_key: "mark-cle:cle-m" },
                tts: { provider: "cartesia", api_key: "mark-cle:cle-c" },
                stt: { provider: "soniox", api_key: "mark-cle:cle-s" },
            },
            ["llm", "stt", "tts"],
            DEFAUTS,
        );
        expect(corps.byok!.mode).toBe("pipeline");
        expect(corps.byok!.pipeline!.embeddings).toBeUndefined();
    });

    it("sur une configuration complète, la fenêtre ne montre que sa brique", () => {
        expect(segmentsDeLaFenetre("tts", "chaine", existantDuMode(CHAINE, {}, "chaine"), DEFAUTS)).toEqual(["tts"]);
    });

    it("le temps réel enregistre le modèle temps réel et le cerveau, sans la voix ni la transcription", () => {
        const existant = existantDuMode(CHAINE, {}, "temps-reel");
        const corps = construireCorps(
            "temps-reel",
            existant,
            { realtime: { provider: "openai_realtime", api_key: "mark-cle:cle-o", model: "gpt-realtime" } },
            ["realtime"],
            DEFAUTS,
        );
        expect(corps.byok!.mode).toBe("realtime");
        expect(corps.byok!.realtime!.realtime).toMatchObject({ provider: "openai_realtime" });
        expect((corps.byok!.realtime!.llm as { provider: string }).provider).toBe("mistral");
        expect(corps.byok!.pipeline).toBeUndefined();
    });

    it("un fournisseur « dograh » (crédits de l'amont) est refusé", () => {
        const existant = existantDuMode(CHAINE, {}, "chaine");
        expect(() =>
            construireCorps("chaine", existant, { llm: { provider: "dograh", api_key: "x" } }, ["llm"], DEFAUTS),
        ).toThrow(ConfigurationIncomplete);
    });
});

describe("deux configurations gardées (lot 13, SE-24)", () => {
    const LES_DEUX = {
        version: 2,
        mode: "byok",
        byok: { mode: "realtime", pipeline: CHAINE.byok.pipeline, realtime: TEMPS_REEL.byok.realtime },
    };
    const SORTIE_REALTIME = { realtime: { provider: "openai_realtime", api_key: "mark-cle:cle-o", model: "gpt-realtime-2" } };

    it("lit chaque mode dans sa propre configuration, active ou non", () => {
        const chaine = existantDuMode(LES_DEUX, null, "chaine");
        expect(vueDeLaBrique(chaine, "tts")).toMatchObject({ fournisseur: "cartesia", modele: "sonic-3.6" });
        expect(vueDeLaBrique(chaine, "stt")).toMatchObject({ fournisseur: "soniox" });
        const reel = existantDuMode(LES_DEUX, null, "temps-reel");
        expect(vueDeLaBrique(reel, "realtime")).toMatchObject({ modele: "gpt-realtime" });
        expect(modeEnregistre(LES_DEUX, null)).toBe("temps-reel");
    });

    it("régler le temps réel reprend la chaîne telle quelle et garde le mode actif", () => {
        const enregistree = { ...LES_DEUX, byok: { ...LES_DEUX.byok, mode: "pipeline" } }; // la chaîne est active
        const corps = construireCorps("temps-reel", existantDuMode(enregistree, null, "temps-reel"), SORTIE_REALTIME, ["realtime"], DEFAUTS, enregistree);
        expect(corps.byok?.mode).toBe("pipeline"); // changer d'onglet n'active rien
        expect(corps.byok?.realtime?.realtime.model).toBe("gpt-realtime-2");
        expect(corps.byok?.pipeline?.tts.provider).toBe("cartesia"); // voix et transcription de la chaîne : toujours là
        expect(corps.byok?.pipeline?.stt.api_key).toBe("****1234");
    });

    it("première configuration : celle qu'on règle devient active ; sans autre mode, rien d'autre n'est envoyé", () => {
        const corps = construireCorps("temps-reel", existantDuMode(TEMPS_REEL, null, "temps-reel"), SORTIE_REALTIME, ["realtime"], DEFAUTS, null);
        expect(corps.byok?.mode).toBe("realtime");
        expect(corps.byok?.pipeline).toBeUndefined();
        const seule = construireCorps("temps-reel", existantDuMode(TEMPS_REEL, null, "temps-reel"), SORTIE_REALTIME, ["realtime"], DEFAUTS, TEMPS_REEL);
        expect(seule.byok?.mode).toBe("realtime");
        expect(seule.byok?.pipeline).toBeUndefined();
    });

    it("dit si un mode a déjà été réglé, et lequel est actif", () => {
        expect(blocEnregistre(CHAINE, "temps-reel")).toBeNull();
        expect(blocEnregistre(LES_DEUX, "temps-reel")).not.toBeNull();
        expect(modeActifEnregistre(LES_DEUX)).toBe("temps-reel");
        expect(modeActifEnregistre({ mode: "dograh" })).toBeNull();
    });
});
