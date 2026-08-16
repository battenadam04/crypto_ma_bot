import type { Metadata } from "next";
import AboutContent from "./AboutContent";

export const metadata: Metadata = {
  title: "About",
  description:
    "Learn about Adam Batten — my mission, values, process, and approach to exceptional web development.",
};

export default function AboutPage() {
  return <AboutContent />;
}
