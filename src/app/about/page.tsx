import type { Metadata } from "next";
import AboutContent from "./AboutContent";

export const metadata: Metadata = {
  title: "About",
  description:
    "Learn about DevCraft Studio — our mission, values, process, and the team behind exceptional web development.",
};

export default function AboutPage() {
  return <AboutContent />;
}
