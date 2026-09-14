import type { SharedReportData } from "../pages/SharedReport";

/**
 * The example study's report, bundled for the homepage's "open the real
 * report" panel.
 *
 * The JSON files are exported from the backend demo fixture
 * (`demo_seeder._v2_report(lang)`, the researcher-refined analysis every
 * new account's demo study ships with), so the panel shows exactly what a
 * signup sees, with no house account, share token or network request.
 * `backend/tests/test_demo_report_bundle.py` fails when the fixture and
 * these files drift; re-export with:
 *
 *   cd backend && python -c "from scripts.export_demo_report import main; main()"
 *
 * Loaded lazily (dynamic import) so the ~10 KB per language never enters
 * the marketing bundle or the prerender.
 */
export async function loadDemoReport(language: string | undefined): Promise<SharedReportData> {
  const fr = (language || "en").toLowerCase().startsWith("fr");
  const mod = fr
    ? await import("./demoReport.fr.json")
    : await import("./demoReport.en.json");
  return mod.default as unknown as SharedReportData;
}
