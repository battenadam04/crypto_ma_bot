import { prisma } from "@/lib/db";
import Hero from "@/components/sections/Hero";
import FeaturedProjects from "@/components/sections/FeaturedProjects";
import ServicesOverview from "@/components/sections/ServicesOverview";
import WhyChooseUs from "@/components/sections/WhyChooseUs";
import Testimonials from "@/components/sections/Testimonials";
import CTASection from "@/components/sections/CTASection";

// Avoid build-time DB access failures on hosts where the DB is prepared in `npm run build`
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [projects, services, testimonials] = await Promise.all([
    prisma.project.findMany({
      where: { featured: true },
      orderBy: { order: "asc" },
      take: 3,
    }),
    prisma.service.findMany({
      orderBy: { order: "asc" },
      take: 6,
    }),
    prisma.testimonial.findMany({
      where: { featured: true },
      take: 3,
    }),
  ]);

  return (
    <>
      <Hero />
      <FeaturedProjects projects={projects} />
      <ServicesOverview services={services} />
      <WhyChooseUs />
      <Testimonials testimonials={testimonials} />
      <CTASection />
    </>
  );
}
