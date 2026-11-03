package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxConfig;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderDispatcher;
import net.minecraft.client.renderer.blockentity.state.BlockEntityRenderState;
import net.minecraft.client.renderer.feature.ModelFeatureRenderer;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** N'affiche pas coffres, panneaux, bannières... au-delà de la distance choisie. */
@Mixin(BlockEntityRenderDispatcher.class)
public abstract class BlockEntityRenderDispatcherMixin {
    @Shadow private Vec3 cameraPos;

    @Inject(method = "tryExtractRenderState", at = @At("HEAD"), cancellable = true)
    private void cronux$cullFar(BlockEntity blockEntity, float partialTick, ModelFeatureRenderer.CrumblingOverlay crumbling,
                                boolean flag, CallbackInfoReturnable<BlockEntityRenderState> cir) {
        int max = CronuxConfig.blockEntityDistance;
        if (max <= 0 || cameraPos == null) return;
        if (blockEntity.getBlockPos().distToCenterSqr(cameraPos) > (double) max * max) cir.setReturnValue(null);
    }
}
