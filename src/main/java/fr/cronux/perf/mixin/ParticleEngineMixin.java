package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxConfig;
import net.minecraft.client.particle.ParticleEngine;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Coupe les particules à la source : ni simulées (CPU), ni dessinées (GPU). */
@Mixin(ParticleEngine.class)
public abstract class ParticleEngineMixin {
    @Inject(method = {"add", "extract"}, at = @At("HEAD"), cancellable = true)
    private void cronux$noParticles(CallbackInfo ci) {
        if (CronuxConfig.noParticles) ci.cancel();
    }
}
