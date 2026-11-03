package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxPerf;
import fr.cronux.perf.FpsPreset;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(targets = "net.minecraft.client.Minecraft", remap = false)
public abstract class MinecraftMixin {
    /** Les Options n'existent qu'à la fin du constructeur. */
    @Inject(method = "<init>", at = @At("TAIL"), remap = false)
    private void cronux$applyPreset(CallbackInfo ci) {
        CronuxPerf.init();
        if (!CronuxPerf.applyPreset) return;
        try {
            FpsPreset.apply(this);
            CronuxPerf.applyPreset = false;
            CronuxPerf.save();
            CronuxPerf.LOG.info("Preset FPS appliqué");
        } catch (Throwable t) {
            CronuxPerf.LOG.error("Échec du preset FPS", t);
        }
    }
}
