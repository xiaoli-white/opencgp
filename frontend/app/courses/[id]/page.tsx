import CourseWorkspace from "@/components/course/CourseWorkspace";

export default function CoursePage({ params }: { params: { id: string } }) {
  return <CourseWorkspace courseId={params.id} />;
}
