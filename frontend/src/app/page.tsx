import HomeClient from "./page-client";
import { RobotScene } from "@/components/RobotScene";

export default function Home() {
  return <HomeClient robotSlot={<RobotScene />} />;
}
