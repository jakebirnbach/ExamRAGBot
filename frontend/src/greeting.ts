export const STUDENT_NAME = "Beverly";

export function timeOfDay(hour: number): "morning" | "afternoon" | "evening" {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  return "evening";
}

export function greeting(now: Date): string {
  return `Good ${timeOfDay(now.getHours())}, ${STUDENT_NAME}`;
}
