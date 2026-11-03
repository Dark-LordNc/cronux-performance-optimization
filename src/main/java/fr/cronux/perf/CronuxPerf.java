package fr.cronux.perf;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/** Config + logger. Aucune dépendance de compilation sur Minecraft ou Fabric : tout passe par réflexion. */
public final class CronuxPerf {
    public static final Logger LOG = LoggerFactory.getLogger("Cronux");
    private static final Properties PROPS = new Properties();
    private static final Path CONFIG = configDir().resolve("cronux.properties");

    /** Applique le preset FPS au prochain démarrage (repasse à false une fois appliqué). */
    public static boolean applyPreset = true;
    /** Supprime le rendu du vignettage (overlay sombre sur les bords de l'écran). */
    public static boolean disableVignette = true;

    static {
        if (Files.exists(CONFIG)) {
            try (Reader r = Files.newBufferedReader(CONFIG)) {
                PROPS.load(r);
            } catch (Exception e) {
                LOG.warn("Impossible de lire {}", CONFIG, e);
            }
        }
        applyPreset = Boolean.parseBoolean(PROPS.getProperty("applyPreset", "true"));
        disableVignette = Boolean.parseBoolean(PROPS.getProperty("disableVignette", "true"));
        save();
        LOG.info("Cronux Performance chargé (applyPreset={}, disableVignette={})", applyPreset, disableVignette);
    }

    private CronuxPerf() {}

    public static void init() {} // force le bloc static

    private static Path configDir() {
        try {
            Class<?> fl = Class.forName("net.fabricmc.loader.api.FabricLoader");
            Object loader = fl.getMethod("getInstance").invoke(null);
            return (Path) fl.getMethod("getConfigDir").invoke(loader);
        } catch (Throwable t) {
            return Path.of("config");
        }
    }

    public static void save() {
        PROPS.setProperty("applyPreset", Boolean.toString(applyPreset));
        PROPS.setProperty("disableVignette", Boolean.toString(disableVignette));
        try {
            Files.createDirectories(CONFIG.getParent());
            try (Writer w = Files.newBufferedWriter(CONFIG)) {
                PROPS.store(w, "Cronux Performance - mettre applyPreset=true pour reappliquer le preset FPS");
            }
        } catch (Exception e) {
            LOG.warn("Impossible d'écrire {}", CONFIG, e);
        }
    }
}
