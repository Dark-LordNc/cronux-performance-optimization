package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxPerf;
import net.minecraft.client.gui.hud.InGameHud;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(InGameHud.class)
public abstract class InGameHudMixin {
    /** Le vignettage est un quad plein écran avec blending dessiné à chaque frame. */
    @Inject(method = "renderVignetteOverlay", at = @At("HEAD"), cancellable = true)
    private void cronux$skipVignette(CallbackInfo ci) {
        if (CronuxPerf.disableVignette) ci.cancel();
    }
}
