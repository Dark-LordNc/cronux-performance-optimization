package fr.cronux.perf;

import net.minecraft.client.CloudStatus;
import net.minecraft.client.GraphicsPreset;
import net.minecraft.client.InactivityFpsLimit;
import net.minecraft.client.Minecraft;
import net.minecraft.client.OptionInstance;
import net.minecraft.client.Options;
import net.minecraft.server.level.ParticleStatus;

/** Presets vidéo : chaque niveau sacrifie un peu plus de qualité pour des FPS. */
public enum FpsPreset {
    /** Bon compromis : distance 8, rendu rapide. */
    EQUILIBRE(8, 1.0, ParticleStatus.DECREASED),
    /** Max FPS jouable : distance 5, entités réduites. */
    FPS_MAX(5, 0.75, ParticleStatus.MINIMAL),
    /** Tout au minimum : distance 2. C'est ce preset qui donne les plus gros chiffres. */
    EXTREME(2, 0.5, ParticleStatus.MINIMAL);

    private final int renderDistance;
    private final double entityScale;
    private final ParticleStatus particles;

    FpsPreset(int renderDistance, double entityScale, ParticleStatus particles) {
        this.renderDistance = renderDistance;
        this.entityScale = entityScale;
        this.particles = particles;
    }

    public void apply(Minecraft mc) {
        Options o = mc.options;
        try {
            o.applyGraphicsPreset(GraphicsPreset.FAST);
        } catch (RuntimeException e) {
            CronuxClient.LOG.warn("Preset graphique FAST non applique", e);
        }
        set(o.enableVsync(), false);
        set(o.framerateLimit(), Options.UNLIMITED_FRAMERATE_CUTOFF);
        set(o.inactivityFpsLimit(), InactivityFpsLimit.MINIMIZED);
        set(o.renderDistance(), renderDistance);
        set(o.simulationDistance(), 5);
        set(o.entityDistanceScaling(), entityScale);
        set(o.cloudStatus(), CloudStatus.OFF);
        set(o.particles(), particles);
        set(o.entityShadows(), false);
        set(o.ambientOcclusion(), false);
        set(o.biomeBlendRadius(), 0);
        set(o.mipmapLevels(), 0);
        set(o.maxAnisotropyBit(), 0);
        set(o.vignette(), false);
        set(o.improvedTransparency(), false);
        set(o.cutoutLeaves(), false);
        set(o.chunkSectionFadeInTime(), 0.0);
        set(o.bobView(), false);

        if (this == EXTREME) {
            CronuxConfig.noWeather = true;
            CronuxConfig.noParticles = true;
            CronuxConfig.entityDistance = 32;
            CronuxConfig.blockEntityDistance = 24;
        } else if (this == FPS_MAX) {
            CronuxConfig.noWeather = true;
            CronuxConfig.entityDistance = 48;
            CronuxConfig.blockEntityDistance = 32;
        }
        CronuxConfig.uncapFps = true;
        CronuxConfig.save();
        o.save();
        CronuxClient.LOG.info("Preset {} applique", this);
    }

    private static <T> void set(OptionInstance<T> option, T value) {
        try {
            option.set(value);
        } catch (RuntimeException e) {
            CronuxClient.LOG.warn("Option {} ignoree", option, e);
        }
    }
}
