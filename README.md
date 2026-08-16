# Adam Batten — Portfolio & Services

A modern, high-performance personal portfolio website built with Next.js 16, TypeScript, and Tailwind CSS. Features a services showcase with pricing estimates, a service request form, project portfolio with filtering, and comprehensive SEO optimization.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (App Router, Server Components) |
| Language | TypeScript |
| Styling | Tailwind CSS 4 with CSS custom properties |
| Database | SQLite via Prisma ORM (no external DB needed) |
| Animations | Framer Motion |
| Forms | React Hook Form + Zod validation |
| Unit Testing | Vitest + Testing Library |
| E2E Testing | Playwright |

## Features

- **Hero Section** — Eye-catching gradient animations, floating elements, code preview, and a first-time user discount offer (WELCOME20)
- **Portfolio** — Project showcase with tag-based filtering and animated cards
- **Services** — Detailed service cards with pricing ranges, delivery estimates, and feature lists
- **Service Request Form** — Full form with dynamic pricing estimates based on selected service, budget range, and timeline selection
- **Contact Form** — Validated contact form with success/error feedback
- **About** — Company values, 4-step process, and tech stack showcase
- **SEO** — Meta tags, Open Graph, Twitter cards, sitemap.xml, robots.txt, semantic HTML, security headers
- **Animations** — Smooth scroll-triggered animations, hover effects, floating elements throughout

## Getting Started

```bash
# Install dependencies
npm install

# Set up environment
cp .env.example .env

# Initialize database + seed sample data
npm run db:setup

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm run start` | Start production server (`0.0.0.0`) |
| `npm run lint` | Run ESLint |
| `npm run test` | Run unit tests (Vitest) |
| `npm run test:e2e` | Run E2E tests (Playwright) |
| `npm run db:setup` | Push schema, generate client, seed data |
| `npm run db:migrate` | Run Prisma migrations |
| `npm run db:generate` | Generate Prisma client |
| `npm run seed` | Seed sample projects/services |

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── api/                # REST API routes
│   │   ├── contact/        # Contact form submissions
│   │   ├── projects/       # Portfolio projects
│   │   ├── services/       # Services catalog
│   │   └── service-requests/ # Service request submissions
│   ├── about/              # About page
│   ├── contact/            # Contact page
│   ├── portfolio/          # Portfolio page with filtering
│   └── services/           # Services page with request form
├── components/
│   ├── forms/              # ContactForm, ServiceRequestForm
│   ├── layout/             # Header, Footer
│   ├── sections/           # Hero, FeaturedProjects, Testimonials, etc.
│   └── ui/                 # Button, Card, Badge, Input, etc.
├── lib/                    # Database, validation schemas, constants
└── __tests__/              # Vitest unit tests
e2e/                        # Playwright E2E tests
prisma/                     # Schema and migrations
```

## Color Palette

The design uses a bright, vibrant color system defined as CSS custom properties in `globals.css`:

- **Brand** (Indigo) — Primary brand color for CTAs, links, highlights
- **Accent** (Pink) — Secondary accent for gradients, hover states
- **Pop** (Orange) — Attention-grabbing elements, offers, badges
- **Success/Warning/Error** — Semantic feedback colors
- **Surface** — Neutral gray scale for backgrounds and text

All colors are available as Tailwind utilities (e.g., `text-brand-600`, `bg-accent-50`).

## Contact form email

Contact and service-request forms email **adambatten@live.co.uk** via [Resend](https://resend.com).

1. Create a free Resend account **using** `adambatten@live.co.uk` (required so the default `onboarding@resend.dev` sender can deliver to that inbox).
2. Create an API key in Resend.
3. Set environment variables locally (`.env`) and in **Vercel → Settings → Environment Variables**:

```env
RESEND_API_KEY=re_xxxxxxxx
CONTACT_TO_EMAIL=adambatten@live.co.uk
```

Optional: after you verify your own domain in Resend, set:

```env
CONTACT_FROM_EMAIL="Adam Batten <hello@yourdomain.com>"
```

Without `RESEND_API_KEY`, submissions still save to the local SQLite DB (useful for tests/dev). On Vercel, set the API key so you actually receive the emails.

## Client portal (OTP)

After work begins, create a **portal** for the client (signed in as admin). Clients open `/portal`, enter their email, and receive a **6-digit PIN** (no passwords). “Forgot PIN” simply emails a new code.

- **Client:** chat + live progress milestones (read-only tracking)
- **Admin** (`ADMIN_EMAIL` / `adambatten@live.co.uk`): same screen, plus controls to update milestones, project status, and summary; create portals from `/portal/home`

Locally without Resend, the PIN is returned as `devCode` in the API response and printed in the server log. Seed includes a demo client: `client@example.com`.

## Testing

```bash
# Unit tests
npm run test

# E2E tests (Playwright — pages, forms, APIs, SEO, accessibility)
npm run test:e2e
```

The E2E suite covers:
- All page loads and content rendering
- Navigation between pages
- Contact form validation and submission
- Service request form with dynamic pricing
- Portfolio filtering by tags
- API endpoint CRUD operations
- SEO (meta tags, sitemap, robots.txt, security headers)
- Accessibility (skip link, ARIA, landmarks, keyboard, reduced motion)
