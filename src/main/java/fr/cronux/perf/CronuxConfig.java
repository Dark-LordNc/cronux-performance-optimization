package fr.cronux.perf;

import net.fabricmc.loader.api.FabricLoader;

import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/** Réglages du mod, sauvegardés dans config/cronux.properties. */
public final class CronuxConfig {
    private static final Path FILE = FabricLoader.getInstance().getConfigDir().resolve("cronux.properties");

    /** Le preset FPS a-t-il déjà été appliqué une première fois ? */
    public static boolean firstLaunchDone = false;
    /** Retire la limite à 60 FPS dans les menus et la limite AFK. */
    public static boolean uncapFps = true;
    /** Compteur de FPS en haut à gauche. */
    public static boolean showFps = true;
    /** Ne dessine pas le ciel (soleil, lune, étoiles, dégradé). */
    public static boolean noSky = false;
    /** Ne dessine pas la pluie / la neige. */
    public static boolean noWeather = true;
    /** Aucune particule (ni créée, ni dessinée). */
    public static boolean noParticles = false;
    /** Ne dessine pas la main / l'objet tenu. */
    public static boolean noHand = false;
    /** Distance max de rendu des entités en blocs (0 = vanilla). */
    public static int entityDistance = 64;
    /** Distance max de rendu des block entities (coffres, panneaux...) en blocs (0 = vanilla). */
    public static int blockEntityDistance = 48;

    private CronuxConfig() {}

    public static void load() {
        Properties p = new Properties();
        if (Files.exists(FILE)) {
            try (Reader r = Files.newBufferedReader(FILE)) {
                p.load(r);
            } catch (Exception e) {
                CronuxClient.LOG.warn("Lecture de {} impossible", FILE, e);
            }
        }
        firstLaunchDone = bool(p, "firstLaunchDone", firstLaunchDone);
        uncapFps = bool(p, "uncapFps", uncapFps);
        showFps = bool(p, "showFps", showFps);
        noSky = bool(p, "noSky", noSky);
        noWeather = bool(p, "noWeather", noWeather);
        noParticles = bool(p, "noParticles", noParticles);
        noHand = bool(p, "noHand", noHand);
        entityDistance = integer(p, "entityDistance", entityDistance);
        blockEntityDistance = integer(p, "blockEntityDistance", blockEntityDistance);
        save();
    }

    public static void save() {
        Properties p = new Properties();
        p.setProperty("firstLaunchDone", Boolean.toString(firstLaunchDone));
        p.setProperty("uncapFps", Boolean.toString(uncapFps));
        p.setProperty("showFps", Boolean.toString(showFps));
        p.setProperty("noSky", Boolean.toString(noSky));
        p.setProperty("noWeather", Boolean.toString(noWeather));
        p.setProperty("noParticles", Boolean.toString(noParticles));
        p.setProperty("noHand", Boolean.toString(noHand));
        p.setProperty("entityDistance", Integer.toString(entityDistance));
        p.setProperty("blockEntityDistance", Integer.toString(blockEntityDistance));
        try {
            Files.createDirectories(FILE.getParent());
            try (Writer w = Files.newBufferedWriter(FILE)) {
                p.store(w, "Cronux Performance - touche O en jeu pour ouvrir l'ecran de reglages");
            }
        } catch (Exception e) {
            CronuxClient.LOG.warn("Ecriture de {} impossible", FILE, e);
        }
    }

    private static boolean bool(Properties p, String k, boolean d) {
        String v = p.getProperty(k);
        return v == null ? d : Boolean.parseBoolean(v.trim());
    }

    private static int integer(Properties p, String k, int d) {
        try {
            return Integer.parseInt(p.getProperty(k, Integer.toString(d)).trim());
        } catch (NumberFormatException e) {
            return d;
        }
    }
}
