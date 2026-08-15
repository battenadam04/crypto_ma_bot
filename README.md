# DevCraft Studio — Business Portfolio & Services

A modern, high-performance business portfolio website built with Next.js 16, TypeScript, and Tailwind CSS. Features a services showcase with pricing estimates, a service request form, project portfolio with filtering, and comprehensive SEO optimization.

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

# Initialize database
npx prisma db push
npx prisma generate

# Seed sample data
node prisma/seed.mjs

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |
| `npm run test` | Run unit tests (Vitest) |
| `npm run test:e2e` | Run E2E tests (Playwright) |
| `npm run db:migrate` | Run Prisma migrations |
| `npm run db:generate` | Generate Prisma client |

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

## Testing

```bash
# Unit tests (15 tests)
npm run test

# E2E tests (56 tests)
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
