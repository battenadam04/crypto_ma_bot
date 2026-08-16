import Database from "better-sqlite3";
import { randomUUID } from "crypto";
import path from "path";

const dbFile =
  process.env.DATABASE_URL?.replace(/^file:/, "") ||
  path.join("prisma", "dev.db");
const db = new Database(dbFile);

function upsertProject(project) {
  const existing = db
    .prepare("SELECT id FROM Project WHERE slug = ?")
    .get(project.slug);
  if (existing) {
    db.prepare(
      `UPDATE Project SET title=?, description=?, longDescription=?, imageUrl=?, tags=?, liveUrl=?, githubUrl=?, featured=?, "order"=?, updatedAt=datetime('now') WHERE slug=?`,
    ).run(
      project.title,
      project.description,
      project.longDescription || null,
      project.imageUrl,
      project.tags,
      project.liveUrl || null,
      project.githubUrl || null,
      project.featured ? 1 : 0,
      project.order,
      project.slug,
    );
  } else {
    db.prepare(
      `INSERT INTO Project (id, title, slug, description, longDescription, imageUrl, tags, liveUrl, githubUrl, featured, "order", createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))`,
    ).run(
      randomUUID(),
      project.title,
      project.slug,
      project.description,
      project.longDescription || null,
      project.imageUrl,
      project.tags,
      project.liveUrl || null,
      project.githubUrl || null,
      project.featured ? 1 : 0,
      project.order,
    );
  }
}

function upsertService(service) {
  const existing = db
    .prepare("SELECT id FROM Service WHERE slug = ?")
    .get(service.slug);
  if (existing) {
    db.prepare(
      `UPDATE Service SET title=?, description=?, features=?, priceFrom=?, priceTo=?, estimatedDays=?, icon=?, popular=?, "order"=?, updatedAt=datetime('now') WHERE slug=?`,
    ).run(
      service.title,
      service.description,
      service.features,
      service.priceFrom,
      service.priceTo,
      service.estimatedDays,
      service.icon,
      service.popular ? 1 : 0,
      service.order,
      service.slug,
    );
  } else {
    db.prepare(
      `INSERT INTO Service (id, title, slug, description, features, priceFrom, priceTo, estimatedDays, icon, popular, "order", createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))`,
    ).run(
      randomUUID(),
      service.title,
      service.slug,
      service.description,
      service.features,
      service.priceFrom,
      service.priceTo,
      service.estimatedDays,
      service.icon,
      service.popular ? 1 : 0,
      service.order,
    );
  }
}

function insertTestimonial(t) {
  const existing = db
    .prepare("SELECT id FROM Testimonial WHERE name = ? AND company = ?")
    .get(t.name, t.company);
  if (!existing) {
    db.prepare(
      `INSERT INTO Testimonial (id, name, role, company, content, rating, imageUrl, featured, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))`,
    ).run(
      randomUUID(),
      t.name,
      t.role,
      t.company,
      t.content,
      t.rating,
      t.imageUrl || null,
      t.featured ? 1 : 0,
    );
  }
}

const projects = [
  { title: "E-Commerce Platform", slug: "ecommerce-platform", description: "A full-stack e-commerce solution with real-time inventory, Stripe payments, and an admin dashboard.", longDescription: "Built a comprehensive e-commerce platform handling thousands of daily transactions. Features include real-time inventory management, multi-currency support, advanced search with filters, wishlist functionality, and a complete admin dashboard for order and product management.", imageUrl: "/images/projects/ecommerce.jpg", tags: "Next.js,TypeScript,PostgreSQL,Stripe,Tailwind CSS", liveUrl: "https://example.com", githubUrl: "https://github.com/example/ecommerce", featured: true, order: 1 },
  { title: "SaaS Analytics Dashboard", slug: "saas-analytics", description: "Real-time analytics dashboard with interactive charts, custom reports, and team collaboration.", longDescription: "Designed and developed a SaaS analytics platform processing millions of events daily. Includes customizable dashboards, real-time data streaming, exportable reports, role-based access control, and webhook integrations.", imageUrl: "/images/projects/analytics.jpg", tags: "React,Node.js,D3.js,WebSocket,Redis", liveUrl: "https://example.com", featured: true, order: 2 },
  { title: "Healthcare Booking System", slug: "healthcare-booking", description: "HIPAA-compliant appointment booking system with video consultations and EHR integration.", longDescription: "Developed a telehealth platform enabling patients to book appointments, conduct video consultations, and securely share medical records. Integrated with major EHR systems and implements end-to-end encryption.", imageUrl: "/images/projects/healthcare.jpg", tags: "Next.js,WebRTC,PostgreSQL,Docker,AWS", liveUrl: "https://example.com", featured: true, order: 3 },
  { title: "Real Estate Marketplace", slug: "real-estate-marketplace", description: "Property listing platform with virtual tours, mortgage calculator, and agent matching.", imageUrl: "/images/projects/realestate.jpg", tags: "Vue.js,Laravel,MySQL,Mapbox,Elasticsearch", liveUrl: "https://example.com", featured: false, order: 4 },
  { title: "Fitness Tracking App", slug: "fitness-tracker", description: "Cross-platform fitness app with workout tracking, nutrition logging, and social features.", imageUrl: "/images/projects/fitness.jpg", tags: "React Native,Node.js,MongoDB,GraphQL", featured: false, order: 5 },
  { title: "Restaurant Management System", slug: "restaurant-management", description: "End-to-end restaurant solution with POS, online ordering, table reservations, and kitchen display.", imageUrl: "/images/projects/restaurant.jpg", tags: "Next.js,TypeScript,PostgreSQL,Socket.io", featured: false, order: 6 },
];

// Solo-freelancer GBP ranges — scoped for one developer, not an agency team.
const services = [
  {
    title: "SEO Landing Page",
    slug: "seo-landing-page",
    description:
      "A single high-converting landing page built for search and leads — ideal for a product launch, local service, or campaign. Designed, built, and handed over by me end to end.",
    features:
      "Mobile-first responsive layout,Clear hero + CTA sections,On-page SEO (titles, meta, headings, schema),Contact or lead-capture form,Analytics & conversion tracking,Fast load / Core Web Vitals focus,Basic copy structure & section wireframe,Deployed live with handover notes",
    priceFrom: 650,
    priceTo: 1800,
    estimatedDays: 8,
    icon: "layout",
    popular: true,
    order: 1,
  },
  {
    title: "Website Fixes & Improvements",
    slug: "website-fixes",
    description:
      "Already have a site that is broken, slow, or awkward on mobile? I diagnose and fix real issues — bugs, forms, layout, content updates, and small feature tweaks — without a full rebuild.",
    features:
      "Bug & broken-link fixes,Form and email delivery repairs,Mobile / responsive layout fixes,Content & image updates,Plugin / dependency conflict fixes,Small feature additions,Speed quick-wins,Clear report of what changed",
    priceFrom: 200,
    priceTo: 900,
    estimatedDays: 5,
    icon: "wrench",
    popular: true,
    order: 2,
  },
  {
    title: "Business Website",
    slug: "business-website",
    description:
      "A polished multi-page site for your business (typically Home, About, Services, Contact). Clean design, solid SEO foundations, and easy for you to keep updated.",
    features:
      "4–8 custom pages,Mobile-responsive design,Contact form with email notifications,On-page SEO foundations,Google Analytics / Search Console setup,Basic blog or news section (optional),Hosting & domain handover,1 revision round included",
    priceFrom: 1200,
    priceTo: 3500,
    estimatedDays: 14,
    icon: "palette",
    popular: false,
    order: 3,
  },
  {
    title: "Online Store / E-Commerce",
    slug: "ecommerce-store",
    description:
      "A practical online shop for a solo build: product catalogue, cart, secure checkout, and order emails. Scoped for real catalogues — not an enterprise marketplace.",
    features:
      "Product catalogue & categories,Shopping cart & checkout,Stripe (or similar) payments,Order confirmation emails,Basic inventory / stock flags,Customer accounts (optional),Mobile-friendly storefront,Admin guidance for adding products",
    priceFrom: 2000,
    priceTo: 6500,
    estimatedDays: 25,
    icon: "shopping-cart",
    popular: false,
    order: 4,
  },
  {
    title: "Custom Web Application",
    slug: "custom-web-app",
    description:
      "A focused web app or internal tool built solo — dashboards, booking flows, client portals, or workflow software. Priced and planned for what one developer can ship well.",
    features:
      "Scoped discovery & build plan,Custom UI for your workflows,Secure login / roles as needed,Database & API backend,Integrations (email, payments, CRMs),Responsive web app,Staging + production deploy,Handover & short support window",
    priceFrom: 3000,
    priceTo: 10000,
    estimatedDays: 30,
    icon: "code",
    popular: false,
    order: 5,
  },
  {
    title: "Speed & SEO Tune-up",
    slug: "speed-seo-tuneup",
    description:
      "Audit and improve an existing site: faster pages, cleaner technical SEO, and fixes that help you rank and convert better — without rebuilding from scratch.",
    features:
      "Technical SEO audit,Core Web Vitals / speed fixes,Meta titles, descriptions & headings,Sitemap & robots cleanup,Schema markup where useful,Image & asset optimisation,Analytics / Search Console check,Prioritised fix list + implementation",
    priceFrom: 350,
    priceTo: 1200,
    estimatedDays: 6,
    icon: "zap",
    popular: false,
    order: 6,
  },
];

const testimonials = [
  { name: "Sarah Chen", role: "CTO", company: "TechFlow Inc.", content: "Exceptional work on our e-commerce platform. The attention to detail and performance optimization exceeded our expectations. Our conversion rate improved by 40%.", rating: 5, featured: true },
  { name: "Marcus Johnson", role: "Founder", company: "GreenLeaf Solutions", content: "Adam delivered our SaaS dashboard ahead of schedule. His expertise in real-time data visualization transformed how we present analytics to our clients.", rating: 5, featured: true },
  { name: "Emily Rodriguez", role: "Product Manager", company: "HealthBridge", content: "Building a HIPAA-compliant platform was complex, but Adam's solution was elegant and secure. Our patients love the seamless booking experience.", rating: 5, featured: true },
  { name: "David Park", role: "CEO", company: "Urban Eats", content: "Our restaurant management system has streamlined operations across all locations. The real-time order tracking alone saved us countless hours — thanks Adam.", rating: 4, featured: false },
];

console.log("Seeding database...");
projects.forEach(upsertProject);
services.forEach(upsertService);

// Drop retired catalogue entries (and any requests tied to them)
const keepSlugs = services.map((s) => s.slug);
const placeholders = keepSlugs.map(() => "?").join(", ");
const obsolete = db
  .prepare(`SELECT id FROM Service WHERE slug NOT IN (${placeholders})`)
  .all(...keepSlugs);
for (const row of obsolete) {
  db.prepare("DELETE FROM ServiceRequest WHERE serviceId = ?").run(row.id);
  db.prepare("DELETE FROM Service WHERE id = ?").run(row.id);
}

testimonials.forEach(insertTestimonial);
console.log("Seeding complete.");
db.close();
