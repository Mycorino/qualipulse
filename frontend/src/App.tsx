import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth, getCachedOnboarded, setCachedOnboarded } from "./hooks/useAuth";
import { getMe } from "./api/auth";
import i18n from "./i18n";
import { ToastProvider } from "./components/Toast";
import ImpersonationBanner from "./components/ImpersonationBanner";
import { captureRefFromUrl } from "./utils/referral";
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

/**
 * lazy() that survives a deploy. When a new build ships, the chunk hashes
 * change; a tab still holding the old index.html will 404 on the dynamic
 * import and crash into the ErrorBoundary ("Une erreur est survenue").
 * Here we catch that once, set a guard flag, and reload to pull the fresh
 * index + chunk manifest — the recovery the user was doing by hand. The
 * sessionStorage guard prevents a reload loop if the import fails for any
 * other reason.
 */
const CHUNK_RELOAD_KEY = "qp_chunk_reloaded";
function lazyWithRetry<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      const mod = await factory();
      sessionStorage.removeItem(CHUNK_RELOAD_KEY);
      return mod;
    } catch (err) {
      if (!sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
        sessionStorage.setItem(CHUNK_RELOAD_KEY, "1");
        window.location.reload();
        // Keep Suspense showing the fallback until the reload takes over.
        return new Promise<{ default: T }>(() => {});
      }
      throw err;
    }
  });
}

const ProjectDetail = lazyWithRetry(() => import("./pages/ProjectDetail"));
const InterviewVerify = lazyWithRetry(() => import("./pages/InterviewVerify"));
const PanelPortal = lazyWithRetry(() => import("./pages/PanelPortal"));
const PanelJoin = lazyWithRetry(() => import("./pages/PanelJoin"));
const PanelJoinConfirm = lazyWithRetry(() => import("./pages/PanelJoinConfirm"));
const ForgotPassword = lazyWithRetry(() => import("./pages/ForgotPassword"));
const ResetPassword = lazyWithRetry(() => import("./pages/ResetPassword"));
const AccountLayout = lazyWithRetry(() => import("./pages/account/AccountLayout"));
const AccountHome = lazyWithRetry(() => import("./pages/account/AccountHome"));
const AccountProfile = lazyWithRetry(() => import("./pages/account/AccountProfile"));
const AccountSecurity = lazyWithRetry(() => import("./pages/account/AccountSecurity"));
const AccountWorkspace = lazyWithRetry(() => import("./pages/account/AccountWorkspace"));
const AccountIntegrations = lazyWithRetry(() => import("./pages/account/AccountIntegrations"));
const AccountBilling = lazyWithRetry(() => import("./pages/account/AccountBilling"));
const SharedReport = lazyWithRetry(() => import("./pages/SharedReport"));
const Welcome = lazyWithRetry(() => import("./pages/Welcome"));
const VerifyEmail = lazyWithRetry(() => import("./pages/VerifyEmail"));
const GoogleFinish = lazyWithRetry(() => import("./pages/GoogleFinish"));
const ImpersonateFinish = lazyWithRetry(() => import("./pages/ImpersonateFinish"));
const Terms = lazyWithRetry(() => import("./pages/Terms"));
const Privacy = lazyWithRetry(() => import("./pages/Privacy"));
const LegalDocument = lazyWithRetry(() => import("./pages/LegalDocument"));
const Admin = lazyWithRetry(() => import("./pages/Admin"));
const AffiliatePortal = lazyWithRetry(() => import("./pages/AffiliatePortal"));
const Blog = lazyWithRetry(() => import("./pages/Blog"));
const BlogPostPage = lazyWithRetry(() => import("./pages/BlogPost"));
const AcceptInvitation = lazyWithRetry(() => import("./pages/AcceptInvitation"));
const QuantiShowcase = lazyWithRetry(() => import("./pages/QuantiShowcase"));
const QuantiReportDemo = lazyWithRetry(() => import("./pages/QuantiReportDemo"));
const SurveyList = lazyWithRetry(() => import("./pages/SurveyList"));
const SurveyEditor = lazyWithRetry(() => import("./pages/SurveyEditor"));
const SurveyPreview = lazyWithRetry(() => import("./pages/SurveyPreview"));
const SurveyDashboardPage = lazyWithRetry(() => import("./pages/SurveyDashboard"));
const PublicResponse = lazyWithRetry(() => import("./pages/PublicResponse"));
const StudyOverview = lazyWithRetry(() => import("./pages/StudyOverview"));
const Reports = lazyWithRetry(() => import("./pages/Reports"));
const NotFound = lazyWithRetry(() => import("./pages/NotFound"));

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
        // Sync i18n language with the server's stored preference so
        // child routes render in the correct locale from the first paint.
        if (me.preferred_language) {
          const current = i18n.language?.startsWith("fr") ? "fr" : "en";
          if (me.preferred_language !== current) {
            i18n.changeLanguage(me.preferred_language);
          }
          localStorage.setItem("qp_language", me.preferred_language);
        }
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
  // Affiliate links land on any public page (/?ref=code); stash the code so
  // it survives navigation to /signup and the Google OAuth round-trip.
  useEffect(() => {
    captureRefFromUrl();
  }, []);

  return (
    <ToastProvider>
    <ImpersonationBanner />
    <Suspense fallback={null}>
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/auth/google/finish" element={<GoogleFinish />} />
      <Route path="/auth/impersonate-finish" element={<ImpersonateFinish />} />
      <Route path="/team/accept" element={<AcceptInvitation />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/dpa" element={<LegalDocument />} />
      <Route path="/subprocessors" element={<LegalDocument />} />
      <Route path="/participant-notice" element={<LegalDocument />} />
      <Route path="/ai-use-policy" element={<LegalDocument />} />
      <Route path="/retention-policy" element={<LegalDocument />} />
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
      <Route path="/i/:token" element={<Interview />} />
      {/* Legacy alias — backend share URLs use /interview/{token}. Keep both. */}
      <Route path="/interview/:token" element={<Interview />} />
      <Route path="/interview/verify/:token" element={<InterviewVerify />} />
      <Route path="/panel" element={<PanelPortal />} />
      <Route path="/panel/confirm" element={<PanelJoinConfirm />} />
      <Route path="/participants" element={<PanelJoin />} />
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
        path="/reports"
        element={
          <OnboardedRoute>
            <Reports />
          </OnboardedRoute>
        }
      />
      <Route
        path="/account"
        element={
          <OnboardedRoute>
            <AccountLayout />
          </OnboardedRoute>
        }
      >
        <Route index element={<AccountHome />} />
        <Route path="profile" element={<AccountProfile />} />
        <Route path="security" element={<AccountSecurity />} />
        <Route path="workspace" element={<AccountWorkspace />} />
        <Route path="integrations" element={<AccountIntegrations />} />
        <Route path="billing" element={<AccountBilling />} />
      </Route>
      {/* Catch-all 404 — renders a real "Page not found" UI with
          noindex,follow so Search Console stops flagging unknown URLs as
          soft 404s. Must stay last; React Router matches in order. */}
      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
    </ToastProvider>
  );
}
