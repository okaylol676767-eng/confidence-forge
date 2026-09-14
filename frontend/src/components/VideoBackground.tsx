"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Full-page looping video background.
 * - muted + playsInline so autoplay is allowed everywhere
 * - fades in once the first frame is decodable (no black flash)
 * - static frame instead of playback under prefers-reduced-motion
 */
export function VideoBackground({ src }: { src: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  // `canplay` can fire before hydration attaches listeners (local assets load
  // fast) — recover by checking readyState on mount.
  useEffect(() => {
    const v = videoRef.current;
    if (v && v.readyState >= 2) setReady(true);
  }, []);

  // Some browsers pause offscreen/tab-hidden video and never resume; nudge it.
  useEffect(() => {
    const onVisible = () => {
      const v = videoRef.current;
      if (
        document.visibilityState === "visible" &&
        v &&
        v.paused &&
        !reducedMotion
      ) {
        void v.play().catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [reducedMotion]);

  return (
    <div aria-hidden className="fixed inset-0 z-0 overflow-hidden">
      <video
        ref={videoRef}
        src={src}
        autoPlay={!reducedMotion}
        loop
        muted
        playsInline
        preload="auto"
        onCanPlay={() => setReady(true)}
        className={`h-full w-full object-cover transition-opacity duration-1000 ${
          ready ? "opacity-100" : "opacity-0"
        }`}
      />
      {/* readability scrim — keeps chat text and glass panels legible over the video */}
      <div className="absolute inset-0 bg-gradient-to-b from-forge-bg/80 via-forge-bg/55 to-forge-bg/90" />
    </div>
  );
}
