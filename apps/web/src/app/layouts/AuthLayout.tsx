import { Outlet } from "@tanstack/react-router";

/**
 * Unauthenticated shell. Navy panel on the left carries the brand; the form
 * sits on the light canvas. The ring motif is used once, as a quiet framing
 * device — a brand element, not decoration.
 */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="relative flex flex-col justify-between overflow-hidden bg-navy-900 px-8 py-10 lg:w-[42%] lg:px-12 lg:py-14">
        <div className="relative z-10">
          <p className="font-display text-3xl font-bold uppercase leading-none tracking-wide text-white lg:text-4xl">
            FOREWARN
          </p>
          <p className="font-display mt-2 text-base font-medium uppercase tracking-[0.25em] text-green-500 lg:text-lg">
            Bangladesh
          </p>
        </div>

        <div className="relative z-10 mt-10 max-w-md">
          <h2 className="font-display text-2xl font-semibold leading-snug text-white lg:text-3xl">
            Turning forecasts into action, before the crisis arrives.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-navy-200">
            The Impact-Based Forecasting Portal brings hazard models, exposure data and
            anticipatory action tracking into one place — so decisions can be made on what the
            weather will <em>do</em>, not just what it will be.
          </p>
        </div>

        <p className="relative z-10 mt-10 text-[11px] leading-relaxed text-navy-200/70">
          A programme of the <span className="text-green-500">Start Bangladesh Hub</span>
        </p>

        {/* Ring motif — used once, cropped off the edge */}
        <svg
          className="pointer-events-none absolute -bottom-24 -right-24 size-80 opacity-[0.13]"
          viewBox="0 0 100 100"
          aria-hidden
        >
          {Array.from({ length: 20 }).map((_, index) => {
            const angle = (index / 20) * 2 * Math.PI;
            const x = 50 + Math.cos(angle) * 38;
            const y = 50 + Math.sin(angle) * 38;
            return (
              <rect
                key={index}
                x={x - 3}
                y={y - 5}
                width="6"
                height="10"
                rx="0.5"
                fill="#36D3AE"
                transform={`rotate(${(index / 20) * 360} ${x} ${y})`}
              />
            );
          })}
        </svg>
      </aside>

      <div className="flex flex-1 items-center justify-center bg-navy-50 px-6 py-12">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
