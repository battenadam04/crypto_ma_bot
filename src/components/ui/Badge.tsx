interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "brand" | "accent" | "success" | "pop";
  className?: string;
}

const variants = {
  default: "bg-surface-100 text-surface-700",
  brand: "bg-brand-100 text-brand-700",
  accent: "bg-accent-100 text-accent-700",
  success: "bg-success-50 text-success-600",
  pop: "bg-pop-100 text-pop-700",
};

export default function Badge({
  children,
  variant = "default",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
