package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxPerf;
import fr.cronux.perf.FpsPreset;
import net.minecraft.client.MinecraftClient;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(MinecraftClient.class)
public abstract class MinecraftClientMixin {
    /** Les GameOptions n'existent qu'à la fin du constructeur, après l'entrypoint client. */
    @Inject(method = "<init>", at = @At("TAIL"))
    private void cronux$applyPreset(CallbackInfo ci) {
        if (!CronuxPerf.applyPreset) return;
        FpsPreset.apply(((MinecraftClient) (Object) this).options);
        CronuxPerf.applyPreset = false;
        CronuxPerf.save();
        CronuxPerf.LOG.info("Preset FPS appliqué");
    }
}
