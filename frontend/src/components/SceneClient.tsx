"use client";

import Spline from "@splinetool/react-spline";
import type { SplineProps } from "@splinetool/react-spline";

/**
 * The Spline runtime draws its "Made in Spline" watermark as a WebGL shader
 * pass (logoOverlayPass) inside the canvas framebuffer — it cannot be hidden
 * with CSS. The runtime exposes pipeline.setWatermark(null) which disables
 * that pass; we call it as soon as the scene Application is ready.
 */
function disableWatermark(app: unknown): void {
  // Debug handle for live inspection (window.__splineApp).
  (window as unknown as Record<string, unknown>).__splineApp = app;

  try {
    type Pipeline = {
      setWatermark?: (tex: unknown) => void;
      watermarkTexture?: unknown;
    };
    type MaybeApp = { _renderer?: { pipeline?: Pipeline } };

    // The runtime applies its "Made in Spline" watermark asynchronously,
    // possibly after onLoad — so keep clearing it for a short window.
    let attempts = 0;
    const clear = () => {
      attempts += 1;
      const pipeline = (app as MaybeApp)?._renderer?.pipeline;
      if (pipeline && typeof pipeline.setWatermark === "function") {
        pipeline.setWatermark(null);
      }
      const stillSet =
        !!pipeline &&
        (pipeline.watermarkTexture !== null &&
          pipeline.watermarkTexture !== undefined);
      if (stillSet && attempts < 40) setTimeout(clear, 250);
    };
    clear();
    // A few extra sweeps to beat the async watermark loader.
    [1500, 4000, 8000].forEach((delay) => setTimeout(clear, delay));
  } catch {
    /* never break the scene over a watermark */
  }
}

export function SceneClient({ scene, ...rest }: SplineProps) {
  return (
    <Spline
      {...rest}
      scene={scene}
      // WASM modules must load from first-party files (see public/spline-wasm)
      // — the default new URL(...) import cannot be bundled by webpack.
      wasmPath="/spline-wasm"
      onLoad={disableWatermark}
    />
  );
}
