import { Link } from "react-router-dom";

export default function Privacy() {
  return (
    <div className="legal-page">
      <div className="legal-container">
        <div className="legal-header">
          <Link to="/" style={{ textDecoration: "none" }}>
            <div className="auth-logo">QualiPulse</div>
          </Link>
          <h1 className="auth-title">Privacy Policy</h1>
        </div>

        <div className="legal-content">
          <h2>1. Introduction</h2>
          <p>
            QualiPulse ("we", "us", "our") is committed to protecting your privacy and complying
            with the General Data Protection Regulation (GDPR) and other applicable data protection
            laws. This policy explains what personal data we collect, how we use it, and your
            rights regarding that data.
          </p>
          <p>
            This policy applies to all users of the QualiPulse platform, including researchers
            (account holders) and interview participants.
          </p>

          <h2>2. Data Controller</h2>
          <p>
            QualiPulse acts as a data processor on behalf of researchers who use the platform.
            Researchers are the data controllers for participant data collected through their
            interviews. For data related to researcher accounts and platform usage, QualiPulse
            acts as the data controller.
          </p>
          <p>
            Contact: <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>
          </p>

          <h2>3. Data We Collect</h2>
          <p>We collect the following categories of personal data:</p>

          <p><strong>Researcher account data:</strong></p>
          <ul>
            <li>Name or company name, email address, and hashed password</li>
            <li>Subscription and billing information (processed by Stripe)</li>
            <li>Research projects, interview guides, and analysis data</li>
          </ul>

          <p><strong>Interview participant data (collected on behalf of researchers):</strong></p>
          <ul>
            <li>Display name, email, profession, age range, and country (all optional, provided by the participant)</li>
            <li>Audio recordings of interview responses</li>
            <li>Transcripts generated from audio recordings</li>
            <li>Screening question responses</li>
          </ul>

          <p><strong>Technical data:</strong></p>
          <ul>
            <li>IP address, browser type, and device information (for security and service operation)</li>
            <li>Usage logs and error reports</li>
          </ul>

          <h2>4. How We Use Your Data</h2>
          <p>We process personal data for the following purposes:</p>
          <ul>
            <li><strong>Service delivery:</strong> To operate the platform, conduct AI-powered interviews, generate transcripts, and produce analysis reports.</li>
            <li><strong>Account management:</strong> To authenticate users, manage subscriptions, and send service-related communications.</li>
            <li><strong>Security:</strong> To detect and prevent fraud, abuse, and unauthorised access.</li>
            <li><strong>Service improvement:</strong> To monitor performance, fix bugs, and improve the user experience. We do not use your research data to train AI models.</li>
          </ul>

          <h2>5. Legal Basis for Processing</h2>
          <p>We process personal data under the following legal bases (GDPR Article 6):</p>
          <ul>
            <li><strong>Contract performance:</strong> Processing necessary to provide the Service you have subscribed to.</li>
            <li><strong>Legitimate interest:</strong> Security monitoring, fraud prevention, and service improvement.</li>
            <li><strong>Consent:</strong> Interview participants provide consent before beginning an interview. Researchers are responsible for ensuring appropriate consent mechanisms.</li>
            <li><strong>Legal obligation:</strong> Where we are required to process data to comply with applicable laws.</li>
          </ul>

          <h2>6. Third-Party Processors</h2>
          <p>
            We use the following third-party services to operate the platform. Each processes data
            under a data processing agreement:
          </p>
          <ul>
            <li><strong>OpenAI</strong> (USA) — Speech-to-text transcription (Whisper) and text-to-speech audio generation. Audio data is sent for processing and is not retained by OpenAI for training purposes.</li>
            <li><strong>Anthropic</strong> (USA) — AI-powered interview orchestration and analysis (Claude). Transcript data is sent for processing and is not used to train Anthropic's models.</li>
            <li><strong>SendGrid</strong> (USA) — Transactional email delivery (verification emails, notifications).</li>
            <li><strong>Stripe</strong> (USA) — Payment processing. We do not store credit card details directly.</li>
            <li><strong>Google Cloud Platform</strong> (EU - Belgium) — Infrastructure hosting and compute.</li>
            <li><strong>Cloudflare</strong> (EU) — Audio file storage (R2).</li>
            <li><strong>Neon</strong> (EU - Frankfurt) — PostgreSQL database hosting.</li>
            <li><strong>Sentry</strong> (optional) — Error tracking and monitoring.</li>
          </ul>
          <p>
            Where data is transferred to processors outside the EU/EEA, we ensure appropriate
            safeguards are in place, such as Standard Contractual Clauses (SCCs) or the
            EU-US Data Privacy Framework.
          </p>

          <h2>7. Data Storage and Security</h2>
          <p>
            Your data is stored on servers located in the European Union (Google Cloud Platform,
            Belgium; Neon PostgreSQL, Frankfurt). Audio files are stored in Cloudflare R2 with
            encryption at rest.
          </p>
          <p>
            We implement appropriate technical and organisational measures to protect your data,
            including encryption in transit (TLS), hashed passwords (bcrypt), access controls,
            and regular security reviews.
          </p>

          <h2>8. Data Retention</h2>
          <ul>
            <li><strong>Account data:</strong> Retained for the duration of your account plus 30 days after deletion to allow data export.</li>
            <li><strong>Interview data:</strong> Retained as long as the associated project exists. Researchers can delete projects and participant data at any time.</li>
            <li><strong>Audio recordings:</strong> Retained as long as the associated interview exists. Deleted when the participant or project is deleted.</li>
            <li><strong>Technical logs:</strong> Retained for up to 90 days for security and debugging purposes.</li>
          </ul>

          <h2>9. Your Rights</h2>
          <p>Under the GDPR, you have the following rights:</p>
          <ul>
            <li><strong>Right of access:</strong> Request a copy of the personal data we hold about you.</li>
            <li><strong>Right to rectification:</strong> Request correction of inaccurate personal data.</li>
            <li><strong>Right to erasure:</strong> Request deletion of your personal data ("right to be forgotten").</li>
            <li><strong>Right to data portability:</strong> Receive your data in a structured, machine-readable format (CSV export is available for interview data).</li>
            <li><strong>Right to restrict processing:</strong> Request that we limit how we process your data.</li>
            <li><strong>Right to object:</strong> Object to processing based on legitimate interest.</li>
            <li><strong>Right to withdraw consent:</strong> Where processing is based on consent, you may withdraw it at any time.</li>
          </ul>
          <p>
            To exercise any of these rights, contact us at{" "}
            <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>. We will respond
            within 30 days.
          </p>
          <p>
            <strong>Interview participants:</strong> If you participated in an interview and wish
            to exercise your rights, you may contact us directly or reach out to the researcher
            who created the interview. Researchers can delete participant data through the platform.
          </p>

          <h2>10. Cookies</h2>
          <p>
            QualiPulse uses only essential cookies and local storage necessary for the operation
            of the Service:
          </p>
          <ul>
            <li><strong>Authentication tokens:</strong> Stored in local storage to maintain your login session.</li>
            <li><strong>Session data:</strong> Stored in session storage to support interview resume functionality.</li>
          </ul>
          <p>
            We do not use tracking cookies, advertising cookies, or third-party analytics cookies.
          </p>

          <h2>11. Children's Privacy</h2>
          <p>
            The Service is not directed at individuals under the age of 18. We do not knowingly
            collect personal data from children. If you believe a child has provided us with
            personal data, please contact us and we will delete it.
          </p>

          <h2>12. Changes to This Policy</h2>
          <p>
            We may update this privacy policy from time to time. We will notify you of material
            changes via email or through the Service at least 30 days before they take effect.
            The "Last updated" date at the bottom of this page indicates when the policy was last
            revised.
          </p>

          <h2>13. Contact and Complaints</h2>
          <p>
            For any questions or concerns about this privacy policy or our data practices, contact
            us at <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>.
          </p>
          <p>
            If you are not satisfied with our response, you have the right to lodge a complaint
            with your local data protection supervisory authority.
          </p>
        </div>

        <p className="legal-updated">Last updated: April 2026</p>
        <div className="legal-back">
          <Link to="/">Back to home</Link>
        </div>
      </div>
    </div>
  );
}
