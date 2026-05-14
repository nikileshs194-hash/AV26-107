"use client";

import dynamic from "next/dynamic";

const FloodMap = dynamic(() => import("@/components/FloodMap"), {
  ssr: false,
});

export default function Home() {
  return <FloodMap />;
}
