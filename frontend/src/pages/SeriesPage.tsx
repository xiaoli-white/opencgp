import { useParams } from "react-router-dom";
import SeriesWorkspace from "@/components/series/SeriesWorkspace";

export default function SeriesPage() {
  const { id } = useParams<{ id: string }>();
  return <SeriesWorkspace seriesId={id ?? ""} />;
}
