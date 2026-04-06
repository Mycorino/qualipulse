import { Link } from "react-router-dom";

export default function Terms() {
  return (
    <div className="legal-page">
      <div className="legal-container">
        <div className="legal-header">
          <Link to="/" style={{ textDecoration: "none" }}>
            <div className="auth-logo">QualiPulse</div>
          </Link>
          <h1 className="auth-title">Terms of Service</h1>
        </div>

        <div className="legal-content">
          <h2>1. Service Description</h2>
          <p>
            QualiPulse ("the Service") is a software-as-a-service platform operated by QualiPulse
            ("we", "us", "our") that enables researchers to create, distribute, and analyse
            AI-driven voice interviews. The Service includes interview creation tools, AI-powered
            transcription and analysis, participant management, and data export capabilities.
          </p>

          <h2>2. Accounts</h2>
          <p>
            To use the Service you must create an account with a valid email address and a secure
            password. You are responsible for maintaining the confidentiality of your credentials
            and for all activity that occurs under your account. You must notify us immediately of
            any unauthorised use.
          </p>
          <p>
            You must be at least 18 years old and have the legal authority to enter into these
            terms. If you are using the Service on behalf of an organisation, you represent that
            you have the authority to bind that organisation to these terms.
          </p>

          <h2>3. Acceptable Use</h2>
          <p>You agree not to:</p>
          <ul>
            <li>Use the Service for any unlawful purpose or in violation of any applicable laws or regulations.</li>
            <li>Collect personal data from interview participants without appropriate legal basis (e.g. consent).</li>
            <li>Upload or transmit content that is defamatory, obscene, fraudulent, or infringes intellectual property rights.</li>
            <li>Attempt to gain unauthorised access to the Service, other accounts, or related systems.</li>
            <li>Interfere with or disrupt the integrity or performance of the Service.</li>
            <li>Reverse-engineer, decompile, or disassemble any part of the Service.</li>
            <li>Use the Service to build a competing product or service.</li>
          </ul>

          <h2>4. Intellectual Property</h2>
          <p>
            The Service, including its design, code, AI models, and documentation, is owned by
            QualiPulse and protected by intellectual property laws. You retain ownership of all
            content you upload or create through the Service, including interview guides,
            transcripts, and analysis data.
          </p>
          <p>
            You grant us a limited licence to process your content solely for the purpose of
            providing and improving the Service. We will not use your research data to train AI
            models or share it with third parties except as described in our Privacy Policy.
          </p>

          <h2>5. Data and Privacy</h2>
          <p>
            Your use of the Service is also governed by our{" "}
            <Link to="/privacy">Privacy Policy</Link>, which describes how we collect, use, store,
            and protect personal data. By using the Service, you acknowledge that you have read and
            understood our Privacy Policy.
          </p>
          <p>
            As a researcher using QualiPulse, you act as a data controller for the personal data
            of your interview participants. You are responsible for ensuring that you have an
            appropriate legal basis for collecting and processing participant data.
          </p>

          <h2>6. Payment Terms</h2>
          <p>
            The Service offers free and paid subscription tiers. Paid plans are billed monthly or
            annually as selected at checkout. All fees are non-refundable except where required by
            law. We reserve the right to change pricing with 30 days' advance notice.
          </p>
          <p>
            If payment fails, we may suspend access to paid features after a grace period. Your
            data will be retained for at least 30 days after suspension to allow you to export it.
          </p>

          <h2>7. Service Availability</h2>
          <p>
            We strive to maintain high availability but do not guarantee uninterrupted access. The
            Service may be temporarily unavailable for maintenance, updates, or circumstances
            beyond our control. We will provide reasonable notice of planned downtime when possible.
          </p>

          <h2>8. Limitation of Liability</h2>
          <p>
            To the maximum extent permitted by law, QualiPulse shall not be liable for any
            indirect, incidental, special, consequential, or punitive damages, including but not
            limited to loss of data, revenue, or business opportunities, arising from your use of
            the Service.
          </p>
          <p>
            Our total aggregate liability for any claims relating to the Service shall not exceed
            the amount you paid us in the twelve months preceding the claim. The Service is
            provided "as is" and "as available" without warranties of any kind, express or implied.
          </p>

          <h2>9. Termination</h2>
          <p>
            You may close your account at any time. We may suspend or terminate your account if
            you violate these terms, if required by law, or if we discontinue the Service. Upon
            termination, we will make your data available for export for at least 30 days.
          </p>

          <h2>10. Changes to Terms</h2>
          <p>
            We may update these terms from time to time. We will notify you of material changes
            via email or through the Service at least 30 days before they take effect. Continued
            use of the Service after changes take effect constitutes acceptance of the updated
            terms.
          </p>

          <h2>11. Governing Law</h2>
          <p>
            These terms are governed by the laws of the European Union and the member state in
            which QualiPulse is established. Any disputes shall be resolved in the competent courts
            of that jurisdiction, without prejudice to any mandatory consumer protection laws that
            may apply to you.
          </p>

          <h2>12. Contact</h2>
          <p>
            If you have questions about these terms, please contact us at{" "}
            <a href="mailto:hello@qualipulse.com">hello@qualipulse.com</a>.
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
