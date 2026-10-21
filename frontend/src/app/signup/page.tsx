"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import AuthCard from "@/components/auth/AuthCard";
import AuthField from "@/components/auth/AuthField";
import NexoraLogo from "@/components/brand/NexoraLogo";
import { useAuth } from "@/context/AuthContext";
import { register } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    setSubmitting(true);
    try {
      await register({ full_name: fullName.trim(), email: email.trim(), password });
      router.push("/login");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to create account.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <AuthLoading />;

  return (
    <AuthCard
      eyebrow="Create your account"
      title="Build your connected knowledge workspace."
      description="Bring your knowledge together and turn information into intelligence."
      footer={<p>Already have an account? <Link href="/login">Sign in</Link></p>}
    >
      <form onSubmit={handleSubmit} className="auth-form">
        <AuthField label="Full name" htmlFor="fullName" icon="user">
          <input id="fullName" type="text" value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Enter your full name" autoComplete="name"
            minLength={2} maxLength={255} required className="auth-input" />
        </AuthField>
        <AuthField label="Email" htmlFor="email" icon="email">
          <input id="email" type="email" value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              if (error === "Email is already registered") setError("");
            }}
            placeholder="you@example.com" autoComplete="email" required className="auth-input" />
        </AuthField>
        <AuthField label="Password" htmlFor="password" icon="password">
          <input id="password" type={showPassword ? "text" : "password"}
            value={password} onChange={(event) => setPassword(event.target.value)}
            placeholder="Create a password" autoComplete="new-password"
            minLength={8} maxLength={128} required className="auth-input auth-input-password" />
          <button type="button" className="auth-password-toggle"
            onClick={() => setShowPassword((current) => !current)}
            aria-label={showPassword ? "Hide password" : "Show password"}>
            {showPassword ? "Hide" : "Show"}
          </button>
        </AuthField>
        <AuthField label="Confirm password" htmlFor="confirmPassword" icon="password">
          <input id="confirmPassword" type={showConfirmPassword ? "text" : "password"}
            value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="Confirm your password" autoComplete="new-password"
            minLength={8} maxLength={128} required className="auth-input auth-input-password" />
          <button type="button" className="auth-password-toggle"
            onClick={() => setShowConfirmPassword((current) => !current)}
            aria-label={showConfirmPassword ? "Hide password confirmation" : "Show password confirmation"}>
            {showConfirmPassword ? "Hide" : "Show"}
          </button>
        </AuthField>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button type="submit" disabled={submitting} className="auth-submit">
          {submitting ? (
            <span className="auth-submit-loading"><span className="auth-spinner" /> Creating account…</span>
          ) : "Create Account"}
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
