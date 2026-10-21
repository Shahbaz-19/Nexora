"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import AuthCard from "@/components/auth/AuthCard";
import AuthField from "@/components/auth/AuthField";
import NexoraLogo from "@/components/brand/NexoraLogo";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <AuthLoading />;

  return (
    <AuthCard
      eyebrow="Welcome back"
      title="Sign in to Nexora"
      description="Continue to your connected knowledge workspace."
      footer={
        <p>
          Don&apos;t have an account? <Link href="/signup">Create account</Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} className="auth-form">
        <AuthField label="Email" htmlFor="email" icon="email">
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
            className="auth-input"
          />
        </AuthField>
        <AuthField label="Password" htmlFor="password" icon="password">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter your password"
            autoComplete="current-password"
            required
            className="auth-input auth-input-password"
          />
          <button
            type="button"
            className="auth-password-toggle"
            onClick={() => setShowPassword((current) => !current)}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </AuthField>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button type="submit" disabled={submitting} className="auth-submit">
          {submitting ? (
            <span className="auth-submit-loading">
              <span className="auth-spinner" /> Signing in…
            </span>
          ) : "Sign In"}
        </button>
      </form>
    </AuthCard>
  );
}

function AuthLoading() {
  return (
    <main className="auth-page" role="status" aria-label="Restoring session">
      <NexoraLogo size={58} decorative />
      <span className="auth-page-spinner" />
    </main>
  );
}
