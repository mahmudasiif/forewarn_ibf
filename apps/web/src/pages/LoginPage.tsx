import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // TODO: replace with POST /api/v1/auth/login once the auth module is built.
  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setTimeout(() => navigate({ to: "/" }), 400);
  }

  return (
    <div>
      <h1 className="font-display text-2xl font-bold uppercase tracking-wide text-navy-900">
        Sign in
      </h1>
      <p className="mt-2 text-sm text-navy-700">
        Use the account issued to you by the Hub secretariat.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-navy-900">
            Email address
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-navy-200 bg-white px-3 py-2 text-sm text-navy-900 outline-none placeholder:text-navy-500 focus:border-green-700 focus:ring-2 focus:ring-green-700/30"
            placeholder="name@organisation.org"
          />
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <label htmlFor="password" className="block text-sm font-medium text-navy-900">
              Password
            </label>
            <a href="#" className="text-xs font-medium text-green-700 hover:underline">
              Forgot password?
            </a>
          </div>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-navy-200 bg-white px-3 py-2 text-sm text-navy-900 outline-none placeholder:text-navy-500 focus:border-green-700 focus:ring-2 focus:ring-green-700/30"
            placeholder="••••••••"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-navy-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-700 disabled:opacity-70"
        >
          {submitting && <Loader2 className="size-4 animate-spin" />}
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-xs leading-relaxed text-navy-500">
        Access is role-based (Super Admin, Admin, Registered Viewer, General Viewer). Contact
        the Hub secretariat if you need your role changed.
      </p>
    </div>
  );
}
