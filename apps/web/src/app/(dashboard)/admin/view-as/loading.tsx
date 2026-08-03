import { RouteLoading } from "@/components/ui/RouteLoading";

// Instant per-segment fallback — paints within one frame of the sidebar click
// while the server streams the page. Shape-matched to the loaded layout.
export default function Loading() {
  return <RouteLoading variant="list" rows={5} />;
}
