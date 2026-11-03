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

    @Override
    public void onInitializeClient() {
        CronuxConfig.load();
        openConfig = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.cronux.config", InputConstants.KEY_O, KeyMapping.Category.MISC));

        ClientTickEvents.END_CLIENT_TICK.register(mc -> {
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
