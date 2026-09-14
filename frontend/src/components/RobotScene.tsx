import { SceneClient } from "./SceneClient";

/**
 * Server wrapper for the 3D scene. Kept as a server component so the scene
 * URL stays renderable on the server; the interactive runtime mounts through
 * the SceneClient boundary (which also strips the watermark overlay).
 */
export function RobotScene() {
  return (
    <SceneClient
      scene="https://prod.spline.design/e4SP8AApi1FTShdz/scene.splinecode"
      className="!h-full !w-full"
    />
  );
}
