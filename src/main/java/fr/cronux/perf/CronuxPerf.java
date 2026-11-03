package fr.cronux.perf;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class CronuxPerf implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("Cronux");

    private static final Path CONFIG = FabricLoader.getInstance().getConfigDir().resolve("cronux.properties");
    private static final Properties PROPS = new Properties();

    /** Applique le preset FPS au prochain démarrage (repasse à false une fois appliqué). */
    public static boolean applyPreset = true;
    /** Supprime le rendu du vignettage (overlay sombre sur les bords de l'écran). */
    public static boolean disableVignette = true;

    @Override
    public void onInitializeClient() {
        load();
        LOG.info("Cronux Performance chargé (applyPreset={}, disableVignette={})", applyPreset, disableVignette);
    }

    private static void load() {
        if (Files.exists(CONFIG)) {
            try (Reader r = Files.newBufferedReader(CONFIG)) {
                PROPS.load(r);
            } catch (IOException e) {
                LOG.warn("Impossible de lire {}", CONFIG, e);
            }
        }
        applyPreset = Boolean.parseBoolean(PROPS.getProperty("applyPreset", "true"));
        disableVignette = Boolean.parseBoolean(PROPS.getProperty("disableVignette", "true"));
        save();
    }

    public static void save() {
        PROPS.setProperty("applyPreset", Boolean.toString(applyPreset));
        PROPS.setProperty("disableVignette", Boolean.toString(disableVignette));
        try {
            Files.createDirectories(CONFIG.getParent());
            try (Writer w = Files.newBufferedWriter(CONFIG)) {
                PROPS.store(w, "Cronux Performance - mettre applyPreset=true pour réappliquer le preset FPS");
            }
        } catch (IOException e) {
            LOG.warn("Impossible d'écrire {}", CONFIG, e);
        }
    }
}
