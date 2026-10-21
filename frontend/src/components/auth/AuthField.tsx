import type { ReactNode } from "react";

type AuthFieldIcon = "email" | "password" | "user";

export default function AuthField({ label, htmlFor, icon, children }: {
  label: string;
  htmlFor: string;
  icon: AuthFieldIcon;
  children: ReactNode;
}) {
  return (
    <div className="auth-field">
      <label htmlFor={htmlFor}>{label}</label>
      <div className="auth-input-wrap">
        <AuthInputIcon icon={icon} />
        {children}
      </div>
    </div>
  );
}

function AuthInputIcon({ icon }: { icon: AuthFieldIcon }) {
  if (icon === "email") return (
    <svg className="auth-input-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <path d="m5 8 7 5 7-5" />
    </svg>
  );
  if (icon === "user") return (
    <svg className="auth-input-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 20c.8-4 3.3-6 7.5-6s6.7 2 7.5 6" />
    </svg>
  );
  return (
    <svg className="auth-input-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="10" width="16" height="10" rx="3" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" />
    </svg>
  );
}
