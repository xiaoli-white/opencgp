import { useParams } from "react-router-dom";
import CourseWorkspace from "@/components/course/CourseWorkspace";

export default function CoursePage() {
  const { id } = useParams<{ id: string }>();
  return <CourseWorkspace courseId={id ?? ""} />;
}
