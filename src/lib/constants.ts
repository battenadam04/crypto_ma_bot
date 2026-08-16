export const SITE_CONFIG = {
  name: "Adam Batten",
  title: "Adam Batten — Web Development & Design",
  description:
    "I build high-performance web applications, e-commerce solutions, and digital experiences that drive business growth. Get a free consultation today.",
  url: process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000",
  ogImage: "/images/og-image.jpg",
  creator: "Adam Batten",
  keywords: [
    "Adam Batten",
    "web development",
    "web design",
    "full-stack development",
    "e-commerce",
    "Next.js",
    "React",
    "TypeScript",
    "custom web application",
    "SEO optimization",
    "UI/UX design",
  ],
};

export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/services", label: "Services" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
] as const;

export const BUDGET_OPTIONS = [
  { value: "under-5k", label: "Under £5,000" },
  { value: "5k-10k", label: "£5,000 — £10,000" },
  { value: "10k-25k", label: "£10,000 — £25,000" },
  { value: "25k-50k", label: "£25,000 — £50,000" },
  { value: "50k-plus", label: "£50,000+" },
] as const;

export const TIMELINE_OPTIONS = [
  { value: "asap", label: "ASAP" },
  { value: "1-2-weeks", label: "1–2 Weeks" },
  { value: "1-month", label: "1 Month" },
  { value: "2-3-months", label: "2–3 Months" },
  { value: "3-plus-months", label: "3+ Months" },
  { value: "flexible", label: "Flexible" },
] as const;

export const SOCIAL_LINKS = {
  github: "https://github.com/battenadam04",
  linkedin: "https://linkedin.com",
  twitter: "https://twitter.com",
} as const;

export const FIRST_TIME_OFFER = {
  title: "First Project Discount",
  description: "20% off your first project with me",
  code: "WELCOME20",
  discount: 20,
} as const;
