package fr.cronux.perf;

import net.minecraft.client.option.GameOptions;
import net.minecraft.client.option.SimpleOption;

/** Réglages vidéo orientés FPS maximum. Appliqués une seule fois : le joueur peut ensuite les modifier. */
public final class FpsPreset {
    private FpsPreset() {}

    public static void apply(GameOptions o) {
        set(o.getEnableVsync(), false);        // VSync bride les FPS à la fréquence de l'écran
        set(o.getMaxFps(), 260);               // 260 = "Illimité" dans Minecraft
        setEnum(o.getGraphicsMode(), "FAST");
        setEnum(o.getCloudRenderMode(), "OFF");
        setEnum(o.getParticles(), "MINIMAL");
        set(o.getEntityShadows(), false);
        set(o.getAo(), false);                 // lissage de l'éclairage
        set(o.getBiomeBlendRadius(), 0);
        set(o.getMipmapLevels(), 0);
        set(o.getViewDistance(), 8);
        set(o.getSimulationDistance(), 5);
        set(o.getEntityDistanceScaling(), 0.75);
        o.write();
    }

    private static <T> void set(SimpleOption<T> option, T value) {
        try {
            option.setValue(value);
        } catch (RuntimeException e) {
            CronuxPerf.LOG.warn("Option ignorée: {}", option, e);
        }
    }

    /** Évite de dépendre du package exact des enums (qui change selon les versions des mappings). */
    @SuppressWarnings({"unchecked", "rawtypes"})
    private static <T> void setEnum(SimpleOption<T> option, String constant) {
        Object current = option.getValue();
        if (current instanceof Enum<?> e) {
            set(option, (T) Enum.valueOf((Class) e.getDeclaringClass(), constant));
        }
    }
}
