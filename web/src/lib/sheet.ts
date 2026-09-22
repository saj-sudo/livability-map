// Bottom-sheet snap logic for phones (SPEC §10 mobile layout). Pure so the drag maths can be
// tested without a DOM: the sheet's visible height is a fraction of the map shell, and a drag
// ends at the nearest snap, nudged one step in the direction of a quick flick.

export type Snap = "peek" | "half" | "full";
export const SNAPS: readonly Snap[] = ["peek", "half", "full"];

/** visible height as a fraction of the container height */
export const SNAP_FRACTIONS: Record<Snap, number> = { peek: 0.14, half: 0.5, full: 0.92 };

/** px/ms above which a drag counts as a flick */
export const FLICK_VELOCITY = 0.4;

export function snapHeight(snap: Snap, containerHeight: number): number {
  return Math.round(SNAP_FRACTIONS[snap] * containerHeight);
}

/** The snap whose height is closest to `height`. */
export function nearestSnap(height: number, containerHeight: number): Snap {
  let best: Snap = "peek";
  let bestDist = Infinity;
  for (const s of SNAPS) {
    const d = Math.abs(snapHeight(s, containerHeight) - height);
    if (d < bestDist) {
      best = s;
      bestDist = d;
    }
  }
  return best;
}

function step(snap: Snap, by: number): Snap {
  const i = Math.min(SNAPS.length - 1, Math.max(0, SNAPS.indexOf(snap) + by));
  return SNAPS[i];
}

/**
 * Where a drag ends. `dragDy` is the pointer's vertical travel in px (positive = down, so the
 * sheet gets shorter); `velocity` is px/ms with the same sign. A flick moves one snap in its
 * direction from the starting snap; otherwise the nearest snap to the dragged height wins.
 */
export function nextSnap(current: Snap, dragDy: number, velocity: number, containerHeight: number): Snap {
  if (Math.abs(velocity) >= FLICK_VELOCITY) return step(current, velocity < 0 ? 1 : -1);
  return nearestSnap(snapHeight(current, containerHeight) - dragDy, containerHeight);
}
