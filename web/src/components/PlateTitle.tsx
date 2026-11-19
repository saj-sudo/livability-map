// The map's title, top left, like the title of an atlas plate (SPEC §10, §13.10). It is the
// page's h1 and it always carries the year and pathway of a projected view. It sits on a
// paper-toned ground (a cartouche) so basemap labels never run through it.

import type { Plate } from "../lib/plate";

export default function PlateTitle({ plate }: { plate: Plate }) {
  return (
    <div className="max-w-[26rem] rounded-panel bg-panel px-2.5 py-1.5 sm:px-3 sm:py-2" data-testid="plate">
      <h1 className="font-serif text-[20px] leading-tight sm:text-[28px]">{plate.title}</h1>
      <p className="mt-1 text-fine leading-snug text-muted sm:text-small">{plate.sub}</p>
    </div>
  );
}
