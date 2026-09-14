"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { SparkIcon } from "./icons";
import { ThoughtBubble } from "./ThoughtBubble";

/** Shown while the Spline scene hydrates — keeps layout stable and fast. */
function RobotFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <motion.div
        animate={{ y: [0, -12, 0], rotate: [0, 1.5, 0, -1.5, 0] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
        className="relative flex h-40 w-40 items-center justify-center sm:h-56 sm:w-56"
      >
        <div className="absolute inset-0 rounded-[38%_62%_55%_45%/45%_42%_58%_55%] bg-gradient-to-br from-forge-lime/20 to-forge-lime/5 blur-xl" />
        <div className="flex h-full w-full items-center justify-center rounded-[38%_62%_55%_45%/45%_42%_58%_55%] border border-forge-lime/25 bg-black/50 backdrop-blur-md">
          <SparkIcon width={44} height={44} className="animate-pulse-glow text-forge-lime" />
        </div>
      </motion.div>
    </div>
  );
}

interface RobotStageProps {
  /** Spline scene rendered on the server, passed through page.tsx. */
  scene: ReactNode;
}

export function RobotStage({
  scene,
  busy = false,
}: RobotStageProps & { busy?: boolean }) {
  // Only mount the WebGL canvas when the stage is actually visible (lg+).
  // Below that the chat panel covers this area — mounting there would waste
  // a multi-MB scene download on small screens.
  const [isWide, setIsWide] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return (
    <section
      className="pointer-events-none absolute inset-y-0 left-0 z-0 hidden w-[46%] items-center justify-center lg:flex"
      aria-label="SPIRAL, your transparent AI guide"
    >
      {/* glow bed behind the robot */}
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[min(58vh,520px)] w-[min(58vh,520px)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-forge-lime/10 blur-[100px]" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[min(44vh,380px)] w-[min(44vh,380px)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-forge-lime/[0.06] blur-[90px] animate-pulse-glow" />

      {/* Spline canvas: interactive only where the robot is, page stays clickable */}
      <div
        className="pointer-events-auto relative h-full max-h-dvh w-full"
        style={{ contain: "strict" }}
      >
        {isWide ? (scene ?? <RobotFallback />) : null}
      </div>

      {/* the bot's "thoughts" — appears/disappears above its head */}
      <ThoughtBubble
        busy={busy}
        className="absolute left-1/2 top-[13%] w-max max-w-[300px] -translate-x-1/2"
      />
    </section>
  );
}

export { RobotFallback };
