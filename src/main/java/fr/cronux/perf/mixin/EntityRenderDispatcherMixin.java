package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxConfig;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.culling.Frustum;
import net.minecraft.client.renderer.entity.EntityRenderDispatcher;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** N'affiche pas les entités au-delà de la distance choisie. */
@Mixin(EntityRenderDispatcher.class)
public abstract class EntityRenderDispatcherMixin {
    @Inject(method = "shouldRender", at = @At("HEAD"), cancellable = true)
    private void cronux$cullFar(Entity entity, Frustum frustum, double camX, double camY, double camZ, float partialTick,
                                CallbackInfoReturnable<Boolean> cir) {
        int max = CronuxConfig.entityDistance;
        if (max <= 0 || entity == Minecraft.getInstance().player) return;
        if (entity.distanceToSqr(camX, camY, camZ) > (double) max * max) cir.setReturnValue(false);
    }
}
