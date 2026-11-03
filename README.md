# Cronux Performance

A client-side Fabric mod for **Minecraft 1.21.1**, built to squeeze out as many FPS as possible.

## What it does
- **FPS preset applied on first launch:** VSync off, unlimited FPS, Fast graphics, clouds and particles off/minimal, no entity shadows, smooth lighting off, biome blend 0, mipmaps 0, render distance 8, simulation distance 5. The preset is applied **once**; you can change your settings afterwards.
- **Skips the vignette**, a full-screen blended quad drawn every frame.
- Configuration lives in `config/cronux.properties`. Set `applyPreset=true` to reapply the preset.

## Getting the most FPS (the mod alone isn't enough)
Install these alongside it (Fabric 1.21.1). They do the heavy lifting:

| Mod | Effect |
|---|---|
| **Sodium** | Rewrites the rendering engine (×2 to ×5 FPS) |
| **Lithium** | Optimizes game logic / ticks |
| **FerriteCore** | Cuts RAM usage |
| **ImmediatelyFast** | Speeds up HUD, text and entity rendering |
| **EntityCulling** | Skips rendering entities you can't see |

Recommended JVM arguments (launcher → Java arguments):
```
-Xms4G -Xmx4G -XX:+UseZGC -XX:+ZGenerational -XX:+AlwaysPreTouch -XX:+DisableExplicitGC
```

### About "8000 FPS"
Minecraft has no hard limit above "Unlimited". The real ceiling is your CPU/GPU and the scene. With Sodium plus this preset, a powerful PC can reach several thousand FPS looking at the sky or in a small world. In normal play, expect a few hundred to ~1500 FPS on high-end hardware. Your screen only displays its refresh rate (144/240 Hz…) anyway.

## Build
```bash
./gradlew build
```
The jar ends up in `build/libs/`. GitHub Actions also builds it on every push (**Actions** tab → *cronux-performance* artifact).
