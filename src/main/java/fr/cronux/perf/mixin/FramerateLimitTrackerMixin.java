package fr.cronux.perf.mixin;

import com.mojang.blaze3d.platform.FramerateLimitTracker;
import com.mojang.blaze3d.platform.FramerateLimitTracker.FramerateThrottleReason;
import fr.cronux.perf.CronuxConfig;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Vanilla bride à 60 FPS dans les menus et à 10-30 FPS quand on est AFK. */
@Mixin(FramerateLimitTracker.class)
public abstract class FramerateLimitTrackerMixin {
    @Inject(method = "getThrottleReason", at = @At("RETURN"), cancellable = true)
    private void cronux$uncap(CallbackInfoReturnable<FramerateThrottleReason> cir) {
        if (!CronuxConfig.uncapFps) return;
        FramerateThrottleReason r = cir.getReturnValue();
        if (r != FramerateThrottleReason.WINDOW_ICONIFIED && r != FramerateThrottleReason.NONE) {
            cir.setReturnValue(FramerateThrottleReason.NONE);
        }
    }
}
