import MapApp from "../components/MapApp";
import { toClientManifest } from "../lib/clientManifest";
import { dimensionsFrom } from "../lib/dims";
import { loadManifest } from "../lib/manifest";

// Server component: reads manifest.json at build time (SPEC §5, §6.3) and hands the client
// the slice it needs. The page is prerendered to static HTML.
export default async function Home() {
  const manifest = await loadManifest();
  return <MapApp manifest={toClientManifest(manifest)} dims={dimensionsFrom(manifest)} />;
}
