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

const services = [
  { title: "Custom Web Application", slug: "custom-web-app", description: "Full-stack web applications tailored to your business needs. From concept to deployment with ongoing support.", features: "Custom UI/UX Design,Responsive Development,API Integration,Database Architecture,Authentication & Security,Deployment & DevOps", priceFrom: 5000, priceTo: 25000, estimatedDays: 30, icon: "code", popular: true, order: 1 },
  { title: "E-Commerce Solution", slug: "ecommerce-solution", description: "Complete online store setup with payment processing, inventory management, and admin dashboard.", features: "Product Catalog,Shopping Cart & Checkout,Payment Gateway Integration,Order Management,Inventory Tracking,Customer Accounts", priceFrom: 8000, priceTo: 35000, estimatedDays: 45, icon: "shopping-cart", popular: true, order: 2 },
  { title: "Landing Page & Marketing Site", slug: "landing-page", description: "High-converting landing pages and marketing websites optimized for SEO and performance.", features: "Conversion-Optimized Design,SEO Optimization,Analytics Integration,A/B Testing Ready,CMS Integration,Performance Optimization", priceFrom: 2000, priceTo: 8000, estimatedDays: 14, icon: "layout", popular: false, order: 3 },
  { title: "API Development & Integration", slug: "api-development", description: "RESTful or GraphQL APIs, third-party integrations, and microservice architecture.", features: "RESTful API Design,GraphQL Implementation,Third-Party Integrations,Authentication & Authorization,Rate Limiting & Caching,Documentation", priceFrom: 3000, priceTo: 15000, estimatedDays: 21, icon: "server", popular: false, order: 4 },
  { title: "UI/UX Design & Prototyping", slug: "ui-ux-design", description: "User-centered design with wireframes, prototypes, and design systems for digital products.", features: "User Research,Wireframing,Interactive Prototypes,Design System,Usability Testing,Responsive Design", priceFrom: 3000, priceTo: 12000, estimatedDays: 21, icon: "palette", popular: false, order: 5 },
  { title: "Performance & SEO Optimization", slug: "performance-seo", description: "Speed up your website, improve search rankings, and boost organic traffic.", features: "Core Web Vitals Optimization,Technical SEO Audit,Content Strategy,Schema Markup,Site Speed Optimization,Analytics Setup", priceFrom: 1500, priceTo: 6000, estimatedDays: 10, icon: "zap", popular: false, order: 6 },
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
testimonials.forEach(insertTestimonial);
console.log("Seeding complete.");
db.close();
