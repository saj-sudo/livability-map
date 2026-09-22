// Named weight sets for the My-priorities view (SPEC §20.5). Weights are 0-5 per dimension id;
// `pol` and `race` carry the person's pick for the signed and composition dimensions.

export type PolPick = "left" | "right" | "competitive";
export type RacePick = "w" | "b" | "h" | "a" | "o" | "diverse";

export interface Preset {
  id: string;
  name: string;
  blurb: string;
  weights: Record<string, number>;
  pol?: PolPick;
  race?: RacePick;
}

export const PRESETS: Preset[] = [
  {
    id: "early",
    name: "Early career",
    blurb: "jobs, transit, housing cost, low climate exposure",
    weights: { jobs: 3, transit: 2, house: 2, heat: 1, rflood: 1, cflood: 1, wstress: 1 },
  },
  {
    id: "kids",
    name: "Raising kids",
    blurb: "schools, low exposure, housing, healthcare",
    weights: { school: 3, house: 2, health: 2, heat: 1, rflood: 1, cflood: 1, wstress: 1 },
  },
  {
    id: "queer",
    name: "Queer and looking for community",
    blurb: "LGBTQ+ presence, politics (left lean), jobs",
    weights: { lgbtq: 3, pol: 2, jobs: 2 },
    pol: "left",
  },
  {
    id: "retiring",
    name: "Retiring",
    blurb: "healthcare, heat, low exposure, wellbeing",
    weights: { health: 3, heat: 2, rflood: 1, cflood: 1, wstress: 1, wb: 2 },
  },
  {
    id: "climate",
    name: "Climate first",
    blurb: "the four hazards only",
    weights: { heat: 1, rflood: 1, cflood: 1, wstress: 1 },
  },
];

export const presetById = (id: string | null | undefined): Preset | undefined => PRESETS.find((p) => p.id === id);
