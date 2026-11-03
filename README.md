# Cronux Performance 2.0

A client-side Fabric mod for **Minecraft 26.3**, built to push FPS as high as possible.

**Download:** [`release/cronux-performance-2.0.0+mc26.3.jar`](release/cronux-performance-2.0.0+mc26.3.jar)

## Installation
1. Fabric Loader **0.20.1+** for 26.3, plus **Fabric API** (0.165.0+26.3 or newer)
2. Drop the `.jar` into `.minecraft/mods/`
3. Java 25 (the official launcher provides it)

## Settings
**O key** in game, or **Options → Video → "Cronux Performance (FPS)..."**

| Setting | Effect |
|---|---|
| Preset **Équilibré** | Render distance 8, fast graphics, everything that costs a lot without being visible is turned off |
| Preset **FPS Max** *(applied on first launch)* | Distance 5, entities at 75%, no weather, entities beyond 48 blocks hidden |
| Preset **EXTRÊME** | Distance 2, no particles, entities beyond 32 blocks hidden. The highest numbers |
| Unlock FPS | Removes vanilla's 60 FPS cap in menus and the 10–30 FPS AFK limit |
| FPS counter | Top left, colored (cyan ≥ 1000) |
| Hide sky / weather / particles / hand | Skips those rendering passes. Particles aren't even simulated anymore |
| Entity / chest-and-sign distance | Doesn't draw entities / block entities beyond N blocks |

The presets also set: VSync off, unlimited FPS, clouds off, no entity shadows, no smooth lighting, biome blend 0, mipmaps 0, no vignette, no chunk fade-in, no view bobbing.

## Being honest about "8000 FPS"
The mod removes every limit and every non-essential rendering pass. The final number depends **only on your graphics card and CPU**. With the EXTRÊME preset, the sky hidden, on a powerful PC, you can reach several thousand FPS. On an average PC it will be much less. RAM doesn't make FPS. For even more, add **Sodium** (when available for 26.3).

## Development
- `./gradlew build`: compiles against the real 26.3 client (Loom 1.19, no obfuscation since 26.1)
- CI (`.github/workflows/build.yml`) builds the jar, then **launches Minecraft 26.3** under Xvfb: it checks that every mixin applies, creates a world and plays 20 s with every option enabled
