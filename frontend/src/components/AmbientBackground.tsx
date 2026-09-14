/** Decorative ambient background: aurora glows, starfield, vignette. Pure CSS, zero cost. */
export function AmbientBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {/* aurora glows */}
      <div className="absolute -left-40 -top-44 h-[34rem] w-[34rem] rounded-full bg-forge-lime/[0.07] blur-[110px] animate-pulse-glow" />
      <div
        className="absolute -bottom-48 -right-40 h-[38rem] w-[38rem] rounded-full bg-forge-lime/[0.05] blur-[120px] animate-pulse-glow"
        style={{ animationDelay: "1.4s" }}
      />
      <div
        className="absolute left-1/2 top-1/3 h-[26rem] w-[26rem] -translate-x-1/2 rounded-full bg-forge-lime/[0.04] blur-[100px]"
      />
      {/* grid */}
      <div
        className="absolute inset-0 opacity-[0.13]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(125,211,252,0.16) 1px, transparent 1px), linear-gradient(90deg, rgba(125,211,252,0.16) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage:
            "radial-gradient(ellipse 90% 70% at 50% 45%, black 30%, transparent 75%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 90% 70% at 50% 45%, black 30%, transparent 75%)",
        }}
      />
      {/* starfield */}
      <div
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage:
            "radial-gradient(1.4px 1.4px at 18% 22%, rgba(255,255,255,0.5) 50%, transparent 51%), radial-gradient(1.2px 1.2px at 68% 14%, rgba(255,255,255,0.38) 50%, transparent 51%), radial-gradient(1.6px 1.6px at 84% 38%, rgba(167,139,250,0.5) 50%, transparent 51%), radial-gradient(1.2px 1.2px at 38% 68%, rgba(255,255,255,0.3) 50%, transparent 51%), radial-gradient(1.5px 1.5px at 9% 78%, rgba(198,255,77,0.42) 50%, transparent 51%), radial-gradient(1.3px 1.3px at 56% 88%, rgba(255,255,255,0.34) 50%, transparent 51%), radial-gradient(1.2px 1.2px at 92% 74%, rgba(255,255,255,0.3) 50%, transparent 51%)",
        }}
      />
      {/* vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(2,3,10,0.75)_100%)]" />
    </div>
  );
}
