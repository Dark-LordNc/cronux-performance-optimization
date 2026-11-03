package fr.cronux.perf;

import java.lang.reflect.Method;

/**
 * Réglages vidéo orientés FPS maximum, appliqués une seule fois.
 * Minecraft 26.x n'est plus obfusqué : on utilise les noms officiels (Options / OptionInstance)
 * par réflexion, et chaque réglage absent dans une version est simplement ignoré.
 */
public final class FpsPreset {
    private FpsPreset() {}

    public static void apply(Object minecraft) throws ReflectiveOperationException {
        Object o = minecraft.getClass().getField("options").get(minecraft);
        set(o, "enableVsync", false);        // VSync bride les FPS à la fréquence de l'écran
        set(o, "framerateLimit", 260);       // 260 = "Illimité"
        setEnum(o, "graphicsMode", "FAST");
        setEnum(o, "cloudStatus", "OFF");
        setEnum(o, "particles", "MINIMAL");
        set(o, "entityShadows", false);
        set(o, "ambientOcclusion", false);   // éclairage lisse
        set(o, "biomeBlendRadius", 0);
        set(o, "mipmapLevels", 0);
        set(o, "renderDistance", 8);
        set(o, "simulationDistance", 5);
        set(o, "entityDistanceScaling", 0.75);
        try {
            o.getClass().getMethod("save").invoke(o);
        } catch (ReflectiveOperationException e) {
            CronuxPerf.LOG.warn("Sauvegarde des options impossible", e);
        }
    }

    private static Object option(Object options, String name) {
        try {
            return options.getClass().getMethod(name).invoke(options);
        } catch (ReflectiveOperationException | RuntimeException e) {
            CronuxPerf.LOG.info("Option '{}' absente dans cette version, ignorée", name);
            return null;
        }
    }

    private static void set(Object options, String name, Object value) {
        Object opt = option(options, name);
        if (opt == null) return;
        try {
            for (Method m : opt.getClass().getMethods()) {
                if (m.getName().equals("set") && m.getParameterCount() == 1) {
                    m.invoke(opt, value);
                    return;
                }
            }
        } catch (ReflectiveOperationException | RuntimeException e) {
            CronuxPerf.LOG.warn("Option '{}' ignorée", name, e);
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void setEnum(Object options, String name, String constant) {
        Object opt = option(options, name);
        if (opt == null) return;
        try {
            Object current = opt.getClass().getMethod("get").invoke(opt);
            if (current instanceof Enum<?> e) {
                set(options, name, Enum.valueOf((Class) e.getDeclaringClass(), constant));
            }
        } catch (ReflectiveOperationException | RuntimeException e) {
            CronuxPerf.LOG.info("Option '{}' ignorée ({})", name, e.toString());
        }
    }
}
