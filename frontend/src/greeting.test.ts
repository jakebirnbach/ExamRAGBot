import { describe, expect, it } from "vitest";
import { greeting, timeOfDay } from "./greeting";

describe("timeOfDay", () => {
  it.each([
    [0, "evening"],
    [4, "evening"],
    [5, "morning"],
    [11, "morning"],
    [12, "afternoon"],
    [16, "afternoon"],
    [17, "evening"],
    [23, "evening"],
  ])("hour %i is %s", (hour, expected) => {
    expect(timeOfDay(hour)).toBe(expected);
  });
});

it("greets her by name using local time", () => {
  expect(greeting(new Date(2026, 10, 2, 9))).toBe("Good morning, Beverly");
});
