package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxConfig;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.Hud;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Compteur de FPS en haut à gauche. */
@Mixin(Hud.class)
public abstract class HudMixin {
    @Inject(method = "extractRenderState", at = @At("TAIL"))
    private void cronux$fps(GuiGraphicsExtractor graphics, DeltaTracker delta, CallbackInfo ci) {
        if (!CronuxConfig.showFps || ((Hud) (Object) this).isHidden()) return;
        Minecraft mc = Minecraft.getInstance();
        int fps = mc.getFps();
        int color = fps >= 1000 ? 0xFF55FFFF : fps >= 240 ? 0xFF55FF55 : fps >= 60 ? 0xFFFFFF55 : 0xFFFF5555;
        graphics.text(mc.font, fps + " FPS", 4, 4, color, true);
    }
}
