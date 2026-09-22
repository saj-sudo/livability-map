import { describe, expect, it } from "vitest";
import { nearestSnap, nextSnap, snapHeight } from "./sheet";

const H = 800;

describe("bottom sheet snaps", () => {
  it("maps snaps to heights and back", () => {
    expect(snapHeight("half", H)).toBe(400);
    expect(nearestSnap(390, H)).toBe("half");
    expect(nearestSnap(150, H)).toBe("peek");
    expect(nearestSnap(700, H)).toBe("full");
  });

  it("lands on the nearest snap after a slow drag", () => {
    expect(nextSnap("peek", -250, 0.1, H)).toBe("half"); // dragged up 250px from 112 -> 362
    expect(nextSnap("full", 300, 0.1, H)).toBe("half"); // dragged down from 736 -> 436
    expect(nextSnap("half", 20, 0, H)).toBe("half"); // barely moved
  });

  it("moves one step in the direction of a flick, and clamps at the ends", () => {
    expect(nextSnap("peek", -30, -0.9, H)).toBe("half");
    expect(nextSnap("half", -30, -0.9, H)).toBe("full");
    expect(nextSnap("full", -30, -0.9, H)).toBe("full");
    expect(nextSnap("half", 30, 0.9, H)).toBe("peek");
    expect(nextSnap("peek", 30, 0.9, H)).toBe("peek");
  });
});
