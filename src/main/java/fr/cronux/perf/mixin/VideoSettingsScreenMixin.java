package fr.cronux.perf.mixin;

import fr.cronux.perf.CronuxScreen;
import net.minecraft.client.Options;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.options.OptionsSubScreen;
import net.minecraft.client.gui.screens.options.VideoSettingsScreen;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Ajoute un bouton "Cronux Performance" en haut de Options > Vidéo. */
@Mixin(VideoSettingsScreen.class)
public abstract class VideoSettingsScreenMixin extends OptionsSubScreen {
    private VideoSettingsScreenMixin(Screen parent, Options options, Component title) {
        super(parent, options, title);
    }

    @Inject(method = "addOptions", at = @At("HEAD"))
    private void cronux$addButton(CallbackInfo ci) {
        if (this.list == null) return;
        Screen self = this;
        this.list.addBig(Button.builder(Component.literal("Cronux Performance (FPS)..."),
                b -> this.minecraft.gui.setScreen(new CronuxScreen(self))).build());
    }
}
