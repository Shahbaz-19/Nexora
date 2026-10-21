import type { ReactNode } from "react";

import NexoraLogo from "@/components/brand/NexoraLogo";

interface AuthCardProps {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}

export default function AuthCard({
  eyebrow,
  title,
  description,
  children,
  footer,
}: AuthCardProps) {
  return (
    <main className="auth-page">
      <div className="auth-decoration auth-decoration-left" aria-hidden="true" />
      <div className="auth-decoration auth-decoration-right" aria-hidden="true" />
      <section className="auth-card" aria-labelledby="auth-title">
        <NexoraLogo size={66} className="auth-floating-logo" decorative />
        <div className="auth-brand">Nexora</div>
        <p className="auth-eyebrow">{eyebrow}</p>
        <h1 id="auth-title">{title}</h1>
        <p className="auth-description">{description}</p>
        {children}
        <div className="auth-footer">{footer}</div>
      </section>
    </main>
  );
}
