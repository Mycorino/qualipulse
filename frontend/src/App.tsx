import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth, getCachedOnboarded, setCachedOnboarded } from "./hooks/useAuth";
import { getMe } from "./api/auth";
import { ToastProvider } from "./components/Toast";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";
import ProjectDetail from "./pages/ProjectDetail";
import Interview from "./pages/Interview";
import InterviewVerify from "./pages/InterviewVerify";
import CreateProjectWizard from "./pages/CreateProjectWizard";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import AccountSettings from "./pages/AccountSettings";
import Marketing from "./pages/Marketing";
import SharedReport from "./pages/SharedReport";
import Welcome from "./pages/Welcome";
import VerifyEmail from "./pages/VerifyEmail";
import Terms from "./pages/Terms";
import Privacy from "./pages/Privacy";
import Admin from "./pages/Admin";
import AffiliatePortal from "./pages/AffiliatePortal";
import Blog from "./pages/Blog";
import BlogPostPage from "./pages/BlogPost";
import AcceptInvitation from "./pages/AcceptInvitation";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/**
 * Guards routes that require onboarding to be completed. If the cached flag
 * is missing (e.g. old session, refresh after deploy), we fetch /auth/me
 * once, write the result to the cache, and then render or redirect.
 *
 * This prevents the "clicked back from /welcome and landed on the dashboard
 * with onboarding half-done" bug.
 */
function OnboardedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const cached = getCachedOnboarded();
  const [status, setStatus] = useState<"checking" | "onboarded" | "incomplete">(
    cached === true ? "onboarded" : cached === false ? "incomplete" : "checking"
  );

  useEffect(() => {
    if (!isAuthenticated) return;
    if (cached !== null) return;
    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled) return;
        setCachedOnboarded(!!me.onboarding_completed);
        setStatus(me.onboarding_completed ? "onboarded" : "incomplete");
      })
      .catch(() => {
        // If /auth/me fails (401, network), fall through — ProtectedRoute
        // or the API interceptor will handle auth expiry.
        if (!cancelled) setStatus("onboarded");
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, cached]);

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (status === "checking") return null;
  if (status === "incomplete") return <Navigate to="/welcome" replace />;
  return <>{children}</>;
}

function HomeRoute() {
  const { isAuthenticated } = useAuth();
  const cached = getCachedOnboarded();
  if (!isAuthenticated) return <Marketing />;
  if (cached === false) return <Navigate to="/welcome" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <ToastProvider>
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/team/accept" element={<AcceptInvitation />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route
        path="/welcome"
        element={
          <ProtectedRoute>
            <Welcome />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <OnboardedRoute>
            <Dashboard />
          </OnboardedRoute>
        }
      />
      <Route
        path="/projects/:id"
        element={
          <OnboardedRoute>
            <ProjectDetail />
          </OnboardedRoute>
        }
      />
      <Route
        path="/projects/new"
        element={
          <OnboardedRoute>
            <CreateProjectWizard />
          </OnboardedRoute>
        }
      />
      <Route
        path="/projects/:id/edit"
        element={
          <OnboardedRoute>
            <CreateProjectWizard />
          </OnboardedRoute>
        }
      />
      <Route path="/i/:token" element={<Interview />} />
      <Route path="/interview/verify/:token" element={<InterviewVerify />} />
      <Route path="/reports/:token" element={<SharedReport />} />
      <Route path="/affiliate/:section" element={<AffiliatePortal />} />
      <Route path="/affiliate" element={<Navigate to="/affiliate/apply" replace />} />
      <Route path="/blog" element={<Blog />} />
      <Route path="/blog/:slug" element={<BlogPostPage />} />
      <Route path="/admin" element={<Admin />} />
      <Route
        path="/account"
        element={
          <OnboardedRoute>
            <AccountSettings />
          </OnboardedRoute>
        }
      />
    </Routes>
    </ToastProvider>
  );
}
