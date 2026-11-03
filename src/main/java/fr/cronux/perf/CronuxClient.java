package fr.cronux.perf;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.minecraft.client.KeyMapping;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CronuxClient implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("Cronux");

    private static KeyMapping openConfig;
    /** -Dcronux.audit=true : force l'application de tous les mixins (test automatique). */
    private static final boolean AUDIT = Boolean.getBoolean("cronux.audit");
    private static int auditTicks, worldTicks;

    /** Test uniquement : ouvre "Créer un monde" puis valide, par réflexion (API interne). */
    private static void createTestWorld(net.minecraft.client.Minecraft mc) {
        try {
            Class<?> cws = Class.forName("net.minecraft.client.gui.screens.worldselection.CreateWorldScreen");
            Object screen = mc.gui.screen();
            if (!cws.isInstance(screen)) {
                java.lang.reflect.Method best = null;
                for (java.lang.reflect.Method m : cws.getMethods()) {
                    if (m.getName().equals("openFresh") && java.lang.reflect.Modifier.isStatic(m.getModifiers())
                            && (best == null || m.getParameterCount() < best.getParameterCount())) best = m;
                }
                Object[] args = new Object[best.getParameterCount()];
                Class<?>[] types = best.getParameterTypes();
                for (int i = 0; i < args.length; i++) {
                    if (types[i] == net.minecraft.client.Minecraft.class) args[i] = mc;
                    else if (types[i] == Runnable.class) args[i] = (Runnable) () -> {};
                    else if (net.minecraft.client.gui.screens.Screen.class.isAssignableFrom(types[i])) args[i] = screen;
                    else args[i] = findStatic(types[i], cws);
                }
                LOG.info("CRONUX-TEST openFresh{} -> {}", java.util.Arrays.toString(types), java.util.Arrays.toString(args));
                best.invoke(null, args);
            } else {
                java.lang.reflect.Method create = cws.getDeclaredMethod("onCreate");
                create.setAccessible(true);
                create.invoke(screen);
                LOG.info("CRONUX-TEST onCreate called");
            }
        } catch (Throwable t) {
            LOG.error("CRONUX-TEST world creation failed (screen={})", mc.gui.screen(), t);
        }
    }

    /** Cherche une valeur statique du type voulu (champ ou méthode sans argument). */
    private static Object findStatic(Class<?> type, Class<?>... owners) throws ReflectiveOperationException {
        java.util.List<Class<?>> all = new java.util.ArrayList<>(java.util.List.of(owners));
        all.add(type);
        for (Class<?> c : all) {
            for (java.lang.reflect.Field f : c.getDeclaredFields()) {
                if (java.lang.reflect.Modifier.isStatic(f.getModifiers()) && type.isAssignableFrom(f.getType())) {
                    f.setAccessible(true);
                    return f.get(null);
                }
            }
            for (java.lang.reflect.Method m : c.getDeclaredMethods()) {
                if (java.lang.reflect.Modifier.isStatic(m.getModifiers()) && m.getParameterCount() == 0
                        && type.isAssignableFrom(m.getReturnType())) {
                    m.setAccessible(true);
                    return m.invoke(null);
                }
            }
        }
        LOG.warn("CRONUX-TEST no static {} found", type.getName());
        return null;
    }

    private static void auditTick(net.minecraft.client.Minecraft mc) {
        if (auditTicks++ == 0) {
            try {
                org.spongepowered.asm.mixin.MixinEnvironment.getCurrentEnvironment().audit();
                LOG.info("CRONUX-AUDIT-OK");
            } catch (Throwable t) {
                LOG.error("CRONUX-AUDIT-FAIL", t);
                mc.stop();
            }
            CronuxConfig.noSky = CronuxConfig.noParticles = CronuxConfig.noHand = CronuxConfig.noWeather = true;
            CronuxConfig.entityDistance = 16;
            CronuxConfig.blockEntityDistance = 16;
        }
        if (mc.level != null && mc.player != null) {
            worldTicks++;
            if (worldTicks == 100) mc.gui.setScreen(new CronuxScreen(null));
            if (worldTicks == 140) mc.gui.setScreen(null);
            if (worldTicks % 40 == 0) LOG.info("CRONUX-WORLD tick={} fps={}", worldTicks, mc.getFps());
            if (worldTicks >= 400) {
                LOG.info("CRONUX-WORLD-OK");
                mc.stop();
            }
        } else if (auditTicks == 200 || auditTicks == 260) {
            createTestWorld(mc);
        } else if (auditTicks > 6000) {
            LOG.error("CRONUX-WORLD-TIMEOUT");
            mc.stop();
        }
    }

    @Override
    public void onInitializeClient() {
        CronuxConfig.load();
        openConfig = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.cronux.config", InputConstants.KEY_O, KeyMapping.Category.MISC));

        ClientTickEvents.END_CLIENT_TICK.register(mc -> {
            if (AUDIT) auditTick(mc);
            if (!CronuxConfig.firstLaunchDone) {
                CronuxConfig.firstLaunchDone = true;
                FpsPreset.FPS_MAX.apply(mc);
            }
            while (openConfig.consumeClick()) {
                mc.gui.setScreen(new CronuxScreen(mc.gui.screen()));
            }
        });
        LOG.info("Cronux Performance charge - touche O pour les reglages");
    }
}
