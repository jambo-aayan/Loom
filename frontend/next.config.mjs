/** @type {import('next').NextConfig} */
const nextConfig = {
  // Commit this build came from, shown in the footer (T0.1). Vercel sets VERCEL_GIT_COMMIT_SHA.
  env: { NEXT_PUBLIC_BUILD_SHA: process.env.VERCEL_GIT_COMMIT_SHA ?? "local" },
};

export default nextConfig;
