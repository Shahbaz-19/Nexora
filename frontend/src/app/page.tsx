"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import NexoraLogo from "@/components/brand/NexoraLogo";


export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();


  useEffect(() => {
    if (loading) {
      return;
    }

    if (user) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [user, loading, router]);


  return (
    <main className="flex h-screen flex-col items-center justify-center gap-4 bg-[#FCFBF8]" role="status" aria-label="Loading Nexora">
      <NexoraLogo size={54} decorative />
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#F8E7C9] border-t-[#064E3B]" />
    </main>
  );
}
