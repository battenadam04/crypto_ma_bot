import type { Metadata } from "next";
import ContactContent from "./ContactContent";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Get in touch with Adam Batten. Send me a message, request a quote, or schedule a free consultation.",
};

export default function ContactPage() {
  return <ContactContent />;
}
