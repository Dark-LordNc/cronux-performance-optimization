package fr.cronux.perf;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.CycleButton;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.function.Consumer;
import java.util.function.IntConsumer;

/** Écran de réglages (touche O ou bouton dans Options > Vidéo). */
public class CronuxScreen extends Screen {
    private static final int W = 150, H = 20, GAP = 4;
    private static final Integer[] DISTANCES = {0, 16, 24, 32, 48, 64, 96, 128};

    private final Screen parent;

    public CronuxScreen(Screen parent) {
        super(Component.literal("Cronux Performance"));
        this.parent = parent;
    }

    @Override
    protected void init() {
        int left = width / 2 - W - GAP / 2;
        int right = width / 2 + GAP / 2;
        int y = 32;

        addRenderableWidget(Button.builder(Component.literal("Preset : Equilibre"), b -> preset(FpsPreset.EQUILIBRE))
                .bounds(width / 2 - 154, y, 100, H).build());
        addRenderableWidget(Button.builder(Component.literal("Preset : FPS Max"), b -> preset(FpsPreset.FPS_MAX))
                .bounds(width / 2 - 50, y, 100, H).build());
        addRenderableWidget(Button.builder(Component.literal("Preset : EXTREME"), b -> preset(FpsPreset.EXTREME))
                .bounds(width / 2 + 54, y, 100, H).build());
        y += H + GAP * 3;

        toggle(left, y, "Debloquer FPS (menus/AFK)", CronuxConfig.uncapFps, v -> CronuxConfig.uncapFps = v);
        toggle(right, y, "Compteur FPS", CronuxConfig.showFps, v -> CronuxConfig.showFps = v);
        y += H + GAP;
        toggle(left, y, "Cacher le ciel", CronuxConfig.noSky, v -> CronuxConfig.noSky = v);
        toggle(right, y, "Cacher pluie/neige", CronuxConfig.noWeather, v -> CronuxConfig.noWeather = v);
        y += H + GAP;
        toggle(left, y, "Aucune particule", CronuxConfig.noParticles, v -> CronuxConfig.noParticles = v);
        toggle(right, y, "Cacher la main", CronuxConfig.noHand, v -> CronuxConfig.noHand = v);
        y += H + GAP;
        distance(left, y, "Dist. entites", CronuxConfig.entityDistance, v -> CronuxConfig.entityDistance = v);
        distance(right, y, "Dist. coffres/panneaux", CronuxConfig.blockEntityDistance, v -> CronuxConfig.blockEntityDistance = v);
        y += H + GAP * 3;

        addRenderableWidget(Button.builder(Component.literal("Termine"), b -> onClose())
                .bounds(width / 2 - 100, y, 200, H).build());
    }

    private void toggle(int x, int y, String label, boolean value, Consumer<Boolean> setter) {
        addRenderableWidget(CycleButton.onOffBuilder(value)
                .create(x, y, W, H, Component.literal(label), (btn, v) -> setter.accept(v)));
    }

    private void distance(int x, int y, String label, int value, IntConsumer setter) {
        Integer initial = DISTANCES[0];
        for (Integer d : DISTANCES) if (d == value) initial = d;
        addRenderableWidget(CycleButton.<Integer>builder(
                        d -> Component.literal(d == 0 ? "Vanilla" : d + " blocs"), initial)
                .withValues(DISTANCES)
                .create(x, y, W, H, Component.literal(label), (btn, v) -> setter.accept(v)));
    }

    private void preset(FpsPreset preset) {
        preset.apply(minecraft);
        rebuildWidgets();
    }

    @Override
    public void onClose() {
        CronuxConfig.save();
        minecraft.gui.setScreen(parent);
    }
}
