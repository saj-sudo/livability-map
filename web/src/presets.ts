// Named weight sets for the My-priorities view (SPEC §20.5). Weights are 0-5 per dimension id;
// `pol` carries the person's pick for the signed dimension. Composition is never weighted (§13.39).

export type PolPick = "left" | "right" | "competitive";

export interface Preset {
  id: string;
  name: string;
  blurb: string;
  weights: Record<string, number>;
  pol?: PolPick;
}

export const PRESETS: Preset[] = [
  {
    id: "early",
    name: "Early career",
    blurb: "jobs, access to a city, transit, housing cost, cost of living, rent, internet, low climate exposure",
    weights: { jobs: 3, city: 1, transit: 2, house: 2, cost: 2, rent: 2, net: 1, heat: 1, rflood: 1, cflood: 1, wstress: 1 },
  },
  {
    id: "kids",
    name: "Raising kids",
    blurb: "schools, clean air, trees, safety from conflict, working water, low exposure, housing, healthcare",
    weights: { school: 3, air: 2, trees: 1, conflict: 2, water: 1, house: 2, health: 2, heat: 1, rflood: 1, cflood: 1, wstress: 1 },
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
    blurb: "healthcare and how far it is (by car and on foot), clean air, heat, low exposure, wellbeing, cost of living",
    weights: { health: 3, care: 2, walkcare: 1, air: 1, heat: 2, rflood: 1, cflood: 1, wstress: 1, wb: 2, cost: 2 },
  },
  {
    id: "climate",
    name: "Climate first",
    blurb: "the four hazards only",
    weights: { heat: 1, rflood: 1, cflood: 1, wstress: 1 },
  },
];

export const presetById = (id: string | null | undefined): Preset | undefined => PRESETS.find((p) => p.id === id);
