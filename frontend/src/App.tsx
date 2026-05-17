import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth, getCachedOnboarded, setCachedOnboarded } from "./hooks/useAuth";
import { getMe } from "./api/auth";
import { ToastProvider } from "./components/Toast";
// Eager-load the hot path: marketing, login, signup, interview, and dashboard
// are what 99% of users see first and we don't want a chunk fetch on first
// paint. Everything else is lazy so the main bundle shrinks from ~1.2MB to
// the critical shell.
import Login from "./pages/Login";
import Signup from "./pages/Signup";
// Sprint 17: the Studies list is the post-login home (it replaced the
// old project-grid Dashboard at /dashboard). Eager-loaded as hot path.
import StudyList from "./pages/StudyList";
import Interview from "./pages/Interview";
import Marketing from "./pages/Marketing";

const ProjectDetail = lazy(() => import("./pages/ProjectDetail"));
const InterviewVerify = lazy(() => import("./pages/InterviewVerify"));
const CreateProjectWizard = lazy(() => import("./pages/CreateProjectWizard"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/ResetPassword"));
const AccountSettings = lazy(() => import("./pages/AccountSettings"));
const SharedReport = lazy(() => import("./pages/SharedReport"));
const Welcome = lazy(() => import("./pages/Welcome"));
const VerifyEmail = lazy(() => import("./pages/VerifyEmail"));
const GoogleFinish = lazy(() => import("./pages/GoogleFinish"));
const Terms = lazy(() => import("./pages/Terms"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Admin = lazy(() => import("./pages/Admin"));
const AffiliatePortal = lazy(() => import("./pages/AffiliatePortal"));
const Blog = lazy(() => import("./pages/Blog"));
const BlogPostPage = lazy(() => import("./pages/BlogPost"));
const AcceptInvitation = lazy(() => import("./pages/AcceptInvitation"));
const QuantiShowcase = lazy(() => import("./pages/QuantiShowcase"));
const QuantiReportDemo = lazy(() => import("./pages/QuantiReportDemo"));
const SurveyList = lazy(() => import("./pages/SurveyList"));
const SurveyEditor = lazy(() => import("./pages/SurveyEditor"));
const SurveyPreview = lazy(() => import("./pages/SurveyPreview"));
const SurveyDashboardPage = lazy(() => import("./pages/SurveyDashboard"));
const PublicResponse = lazy(() => import("./pages/PublicResponse"));
const StudyOverview = lazy(() => import("./pages/StudyOverview"));

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
    <Suspense fallback={null}>
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/auth/google/finish" element={<GoogleFinish />} />
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
      {/* Sprint 17: /dashboard renders the Studies list — one home for
          quanti, quali, and hybrid. The URL stays alive for bookmarks
          and muscle memory; the old project-grid Dashboard is retired. */}
      <Route
        path="/dashboard"
        element={
          <OnboardedRoute>
            <StudyList />
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
      {/* Legacy alias — backend share URLs use /interview/{token}. Keep both. */}
      <Route path="/interview/:token" element={<Interview />} />
      <Route path="/interview/verify/:token" element={<InterviewVerify />} />
      <Route path="/reports/:token" element={<SharedReport />} />
      <Route path="/affiliate/:section" element={<AffiliatePortal />} />
      <Route path="/affiliate" element={<Navigate to="/affiliate/apply" replace />} />
      <Route path="/blog" element={<Blog />} />
      <Route path="/blog/:slug" element={<BlogPostPage />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/design-system/quanti" element={<QuantiShowcase />} />
      <Route path="/design-system/quanti/report" element={<QuantiReportDemo />} />
      <Route
        path="/surveys"
        element={
          <OnboardedRoute>
            <SurveyList />
          </OnboardedRoute>
        }
      />
      <Route
        path="/surveys/:id/edit"
        element={
          <OnboardedRoute>
            <SurveyEditor />
          </OnboardedRoute>
        }
      />
      <Route
        path="/surveys/:id/preview"
        element={
          <OnboardedRoute>
            <SurveyPreview />
          </OnboardedRoute>
        }
      />
      <Route
        path="/surveys/:id/dashboard"
        element={
          <OnboardedRoute>
            <SurveyDashboardPage />
          </OnboardedRoute>
        }
      />
      <Route path="/r/:token" element={<PublicResponse />} />
      <Route
        path="/studies"
        element={
          <OnboardedRoute>
            <StudyList />
          </OnboardedRoute>
        }
      />
      <Route
        path="/studies/:id"
        element={
          <OnboardedRoute>
            <StudyOverview />
          </OnboardedRoute>
        }
      />
      <Route
        path="/account"
        element={
          <OnboardedRoute>
            <AccountSettings />
          </OnboardedRoute>
        }
      />
    </Routes>
    </Suspense>
    </ToastProvider>
  );
}
