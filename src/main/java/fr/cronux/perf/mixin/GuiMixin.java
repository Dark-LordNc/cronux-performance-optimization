package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxPerf;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "net.minecraft.client.gui.Gui", remap = false)
public abstract class GuiMixin {
    /** Le vignettage est un quad plein écran avec blending dessiné à chaque frame. */
    @Inject(method = "renderVignette", at = @At("HEAD"), cancellable = true, remap = false)
    private void cronux$skipVignette(CallbackInfo ci) {
        if (CronuxPerf.disableVignette) ci.cancel();
    }
}
