import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";

function TermsContentEN() {
  return (
    <>
      <h2 id="section-1" style={{ scrollMarginTop: "80px" }}>1. Service Description</h2>
      <p>
        QualiPulse ("the Service") is a software-as-a-service platform operated by QualiPulse
        ("we", "us", "our") that enables researchers to create, distribute, and analyse
        AI-driven voice interviews. The Service includes interview creation tools, AI-powered
        transcription and analysis, participant management, and data export capabilities.
      </p>

      <h2 id="section-2" style={{ scrollMarginTop: "80px" }}>2. Accounts</h2>
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

      <h2 id="section-3" style={{ scrollMarginTop: "80px" }}>3. Acceptable Use</h2>
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

      <h2 id="section-4" style={{ scrollMarginTop: "80px" }}>4. Intellectual Property</h2>
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

      <h2 id="section-5" style={{ scrollMarginTop: "80px" }}>5. Data and Privacy</h2>
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
        Our <Link to="/dpa">Data Processing Agreement</Link> applies where QualiPulse processes
        personal data on your behalf.
      </p>
      <p>
        Your use of AI features is also subject to our{" "}
        <Link to="/ai-use-policy">AI Use Policy</Link>, including restrictions on high-risk,
        sensitive, deceptive, discriminatory, or unlawful uses.
      </p>

      <h2 id="section-6" style={{ scrollMarginTop: "80px" }}>6. Payment Terms</h2>
      <p>
        The Service offers free and paid subscription tiers. Paid plans are billed monthly or
        annually as selected at checkout. All fees are non-refundable except where required by
        law. We reserve the right to change pricing with 30 days' advance notice.
      </p>
      <p>
        If payment fails, we may suspend access to paid features after a grace period. Your
        data will be retained for at least 30 days after suspension to allow you to export it.
      </p>

      <h2 id="section-7" style={{ scrollMarginTop: "80px" }}>7. Service Availability</h2>
      <p>
        We strive to maintain high availability but do not guarantee uninterrupted access. The
        Service may be temporarily unavailable for maintenance, updates, or circumstances
        beyond our control. We will provide reasonable notice of planned downtime when possible.
      </p>

      <h2 id="section-8" style={{ scrollMarginTop: "80px" }}>8. Limitation of Liability</h2>
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

      <h2 id="section-9" style={{ scrollMarginTop: "80px" }}>9. Termination</h2>
      <p>
        You may close your account at any time. We may suspend or terminate your account if
        you violate these terms, if required by law, or if we discontinue the Service. Upon
        termination, we will make your data available for export for at least 30 days.
      </p>

      <h2 id="section-10" style={{ scrollMarginTop: "80px" }}>10. Changes to Terms</h2>
      <p>
        We may update these terms from time to time. We will notify you of material changes
        via email or through the Service at least 30 days before they take effect. Continued
        use of the Service after changes take effect constitutes acceptance of the updated
        terms.
      </p>

      <h2 id="section-11" style={{ scrollMarginTop: "80px" }}>11. Governing Law</h2>
      <p>
        These terms are governed by the laws of the European Union and the member state in
        which QualiPulse is established. Any disputes shall be resolved in the competent courts
        of that jurisdiction, without prejudice to any mandatory consumer protection laws that
        may apply to you.
      </p>

      <h2 id="section-12" style={{ scrollMarginTop: "80px" }}>12. Contact</h2>
      <p>
        If you have questions about these terms, please contact us at{" "}
        <a href="mailto:hello@qualipulse.com">hello@qualipulse.com</a>.
      </p>
    </>
  );
}

function TermsContentFR() {
  return (
    <>
      <h2 id="section-1" style={{ scrollMarginTop: "80px" }}>1. Description du Service</h2>
      <p>
        QualiPulse ({"\u00ab\u00a0"}le Service{"\u00a0\u00bb"}) est une plateforme logicielle en mode SaaS exploit{"\u00e9"}e par QualiPulse
        ({"\u00ab\u00a0"}nous{"\u00a0\u00bb"}, {"\u00ab\u00a0"}notre{"\u00a0\u00bb"}) qui permet aux chercheurs de cr{"\u00e9"}er, diffuser et analyser
        des entretiens vocaux pilot{"\u00e9"}s par intelligence artificielle. Le Service comprend des outils de
        cr{"\u00e9"}ation d{"\u2019"}entretiens, la transcription et l{"\u2019"}analyse assist{"\u00e9"}es par IA, la gestion des
        participants et les fonctionnalit{"\u00e9"}s d{"\u2019"}export de donn{"\u00e9"}es.
      </p>

      <h2 id="section-2" style={{ scrollMarginTop: "80px" }}>2. Comptes</h2>
      <p>
        Pour utiliser le Service, vous devez cr{"\u00e9"}er un compte avec une adresse e-mail valide et un
        mot de passe s{"\u00e9"}curis{"\u00e9"}. Vous {"\u00ea"}tes responsable du maintien de la confidentialit{"\u00e9"} de vos
        identifiants et de toute activit{"\u00e9"} effectu{"\u00e9"}e sous votre compte. Vous devez nous informer
        imm{"\u00e9"}diatement de toute utilisation non autoris{"\u00e9"}e.
      </p>
      <p>
        Vous devez avoir au moins 18 ans et disposer de la capacit{"\u00e9"} juridique pour accepter les
        pr{"\u00e9"}sentes conditions. Si vous utilisez le Service au nom d{"\u2019"}une organisation, vous d{"\u00e9"}clarez
        avoir l{"\u2019"}autorit{"\u00e9"} n{"\u00e9"}cessaire pour engager cette organisation au respect des pr{"\u00e9"}sentes conditions.
      </p>

      <h2 id="section-3" style={{ scrollMarginTop: "80px" }}>3. Utilisation acceptable</h2>
      <p>Vous vous engagez {"\u00e0"} ne pas{"\u00a0"}:</p>
      <ul>
        <li>Utiliser le Service {"\u00e0"} des fins ill{"\u00e9"}gales ou en violation de toute loi ou r{"\u00e9"}glementation applicable.</li>
        <li>Collecter des donn{"\u00e9"}es personnelles de participants sans base juridique appropri{"\u00e9"}e (par exemple, le consentement).</li>
        <li>T{"\u00e9"}l{"\u00e9"}charger ou transmettre du contenu diffamatoire, obsc{"\u00e8"}ne, frauduleux ou portant atteinte aux droits de propri{"\u00e9"}t{"\u00e9"} intellectuelle.</li>
        <li>Tenter d{"\u2019"}obtenir un acc{"\u00e8"}s non autoris{"\u00e9"} au Service, {"\u00e0"} d{"\u2019"}autres comptes ou {"\u00e0"} des syst{"\u00e8"}mes connexes.</li>
        <li>Interf{"\u00e9"}rer avec le fonctionnement ou les performances du Service, ou les perturber.</li>
        <li>Proc{"\u00e9"}der {"\u00e0"} l{"\u2019"}ing{"\u00e9"}nierie inverse, {"\u00e0"} la d{"\u00e9"}compilation ou au d{"\u00e9"}sassemblage de toute partie du Service.</li>
        <li>Utiliser le Service pour d{"\u00e9"}velopper un produit ou service concurrent.</li>
      </ul>

      <h2 id="section-4" style={{ scrollMarginTop: "80px" }}>4. Propri{"\u00e9"}t{"\u00e9"} intellectuelle</h2>
      <p>
        Le Service, y compris sa conception, son code, ses mod{"\u00e8"}les d{"\u2019"}IA et sa documentation, est la
        propri{"\u00e9"}t{"\u00e9"} de QualiPulse et est prot{"\u00e9"}g{"\u00e9"} par les lois relatives {"\u00e0"} la propri{"\u00e9"}t{"\u00e9"} intellectuelle.
        Vous conservez la propri{"\u00e9"}t{"\u00e9"} de tout contenu que vous t{"\u00e9"}l{"\u00e9"}chargez ou cr{"\u00e9"}ez via le Service,
        y compris les guides d{"\u2019"}entretien, les transcriptions et les donn{"\u00e9"}es d{"\u2019"}analyse.
      </p>
      <p>
        Vous nous accordez une licence limit{"\u00e9"}e pour traiter votre contenu aux seules fins de
        fourniture et d{"\u2019"}am{"\u00e9"}lioration du Service. Nous n{"\u2019"}utiliserons pas vos donn{"\u00e9"}es de recherche
        pour entra{"\u00ee"}ner des mod{"\u00e8"}les d{"\u2019"}IA et ne les partagerons pas avec des tiers, sauf dans les
        cas d{"\u00e9"}crits dans notre Politique de Confidentialit{"\u00e9"}.
      </p>

      <h2 id="section-5" style={{ scrollMarginTop: "80px" }}>5. Donn{"\u00e9"}es et confidentialit{"\u00e9"}</h2>
      <p>
        Votre utilisation du Service est {"\u00e9"}galement r{"\u00e9"}gie par notre{" "}
        <Link to="/privacy">Politique de Confidentialit{"\u00e9"}</Link>, qui d{"\u00e9"}crit comment nous collectons,
        utilisons, stockons et prot{"\u00e9"}geons les donn{"\u00e9"}es personnelles. En utilisant le Service, vous
        reconnaissez avoir lu et compris notre Politique de Confidentialit{"\u00e9"}.
      </p>
      <p>
        En tant que chercheur utilisant QualiPulse, vous agissez en qualit{"\u00e9"} de responsable du
        traitement des donn{"\u00e9"}es personnelles de vos participants. Vous {"\u00ea"}tes responsable de vous
        assurer que vous disposez d{"\u2019"}une base juridique appropri{"\u00e9"}e pour la collecte et le traitement
        des donn{"\u00e9"}es des participants. Notre <Link to="/dpa">Accord de traitement des donn{"\u00e9"}es</Link>{" "}
        s{"\u2019"}applique lorsque QualiPulse traite des donn{"\u00e9"}es personnelles pour votre compte.
      </p>
      <p>
        Votre utilisation des fonctionnalit{"\u00e9"}s IA est {"\u00e9"}galement soumise {"\u00e0"} notre{" "}
        <Link to="/ai-use-policy">Politique d{"\u2019"}utilisation de l{"\u2019"}IA</Link>, y compris les restrictions
        relatives aux usages sensibles, {"\u00e0"} haut risque, trompeurs, discriminatoires ou illicites.
      </p>

      <h2 id="section-6" style={{ scrollMarginTop: "80px" }}>6. Conditions de paiement</h2>
      <p>
        Le Service propose des formules d{"\u2019"}abonnement gratuites et payantes. Les formules payantes
        sont factur{"\u00e9"}es mensuellement ou annuellement selon le choix effectu{"\u00e9"} lors de la souscription.
        Tous les frais sont non remboursables, sauf disposition l{"\u00e9"}gale contraire. Nous nous
        r{"\u00e9"}servons le droit de modifier les tarifs moyennant un pr{"\u00e9"}avis de 30 jours.
      </p>
      <p>
        En cas d{"\u2019"}{"\u00e9"}chec de paiement, nous pourrons suspendre l{"\u2019"}acc{"\u00e8"}s aux fonctionnalit{"\u00e9"}s payantes
        apr{"\u00e8"}s un d{"\u00e9"}lai de gr{"\u00e2"}ce. Vos donn{"\u00e9"}es seront conserv{"\u00e9"}es pendant au moins 30 jours apr{"\u00e8"}s
        la suspension afin de vous permettre de les exporter.
      </p>

      <h2 id="section-7" style={{ scrollMarginTop: "80px" }}>7. Disponibilit{"\u00e9"} du Service</h2>
      <p>
        Nous nous effor{"\u00e7"}ons de maintenir une haute disponibilit{"\u00e9"} mais ne garantissons pas un acc{"\u00e8"}s
        ininterrompu. Le Service peut {"\u00ea"}tre temporairement indisponible pour maintenance, mises {"\u00e0"}
        jour ou en raison de circonstances ind{"\u00e9"}pendantes de notre volont{"\u00e9"}. Nous fournirons un
        pr{"\u00e9"}avis raisonnable en cas d{"\u2019"}interruption planifi{"\u00e9"}e lorsque cela est possible.
      </p>

      <h2 id="section-8" style={{ scrollMarginTop: "80px" }}>8. Limitation de responsabilit{"\u00e9"}</h2>
      <p>
        Dans toute la mesure permise par la loi, QualiPulse ne saurait {"\u00ea"}tre tenu responsable de
        tout dommage indirect, accessoire, sp{"\u00e9"}cial, cons{"\u00e9"}cutif ou punitif, y compris, sans s{"\u2019"}y
        limiter, la perte de donn{"\u00e9"}es, de revenus ou d{"\u2019"}opportunit{"\u00e9"}s commerciales, r{"\u00e9"}sultant de
        votre utilisation du Service.
      </p>
      <p>
        Notre responsabilit{"\u00e9"} globale totale pour toute r{"\u00e9"}clamation li{"\u00e9"}e au Service ne saurait
        exc{"\u00e9"}der le montant que vous nous avez vers{"\u00e9"} au cours des douze mois pr{"\u00e9"}c{"\u00e9"}dant la
        r{"\u00e9"}clamation. Le Service est fourni {"\u00ab\u00a0"}en l{"\u2019"}{"\u00e9"}tat{"\u00a0\u00bb"} et {"\u00ab\u00a0"}selon disponibilit{"\u00e9"}{"\u00a0\u00bb"} sans
        garantie d{"\u2019"}aucune sorte, expresse ou implicite.
      </p>

      <h2 id="section-9" style={{ scrollMarginTop: "80px" }}>9. R{"\u00e9"}siliation</h2>
      <p>
        Vous pouvez cl{"\u00f4"}turer votre compte {"\u00e0"} tout moment. Nous pouvons suspendre ou r{"\u00e9"}silier votre
        compte si vous enfreignez les pr{"\u00e9"}sentes conditions, si la loi l{"\u2019"}exige ou si nous cessons
        le Service. En cas de r{"\u00e9"}siliation, nous mettrons vos donn{"\u00e9"}es {"\u00e0"} disposition pour export
        pendant au moins 30 jours.
      </p>

      <h2 id="section-10" style={{ scrollMarginTop: "80px" }}>10. Modification des conditions</h2>
      <p>
        Nous pouvons mettre {"\u00e0"} jour les pr{"\u00e9"}sentes conditions de temps {"\u00e0"} autre. Nous vous informerons
        de toute modification substantielle par e-mail ou via le Service au moins 30 jours avant
        son entr{"\u00e9"}e en vigueur. La poursuite de l{"\u2019"}utilisation du Service apr{"\u00e8"}s l{"\u2019"}entr{"\u00e9"}e en vigueur
        des modifications vaut acceptation des conditions mises {"\u00e0"} jour.
      </p>

      <h2 id="section-11" style={{ scrollMarginTop: "80px" }}>11. Droit applicable</h2>
      <p>
        Les pr{"\u00e9"}sentes conditions sont r{"\u00e9"}gies par le droit de l{"\u2019"}Union europ{"\u00e9"}enne et de l{"\u2019"}{"\u00c9"}tat
        membre dans lequel QualiPulse est {"\u00e9"}tabli. Tout litige sera soumis aux juridictions
        comp{"\u00e9"}tentes de cette juridiction, sans pr{"\u00e9"}judice des dispositions imp{"\u00e9"}ratives de
        protection des consommateurs qui pourraient vous {"\u00ea"}tre applicables.
      </p>

      <h2 id="section-12" style={{ scrollMarginTop: "80px" }}>12. Contact</h2>
      <p>
        Si vous avez des questions concernant les pr{"\u00e9"}sentes conditions, veuillez nous contacter {"\u00e0"}{" "}
        <a href="mailto:hello@qualipulse.com">hello@qualipulse.com</a>.
      </p>
    </>
  );
}

export default function Terms() {
  const { t, i18n } = useTranslation();
  const isFR = i18n.language?.startsWith("fr");
  useHead({ title: `${t("legal.terms.pageTitle")} — QualiPulse` });

  const tocItems: [string, string][] = [
    ["#section-1", t("legal.terms.toc.serviceDescription")],
    ["#section-2", t("legal.terms.toc.accounts")],
    ["#section-3", t("legal.terms.toc.acceptableUse")],
    ["#section-4", t("legal.terms.toc.intellectualProperty")],
    ["#section-5", t("legal.terms.toc.dataAndPrivacy")],
    ["#section-6", t("legal.terms.toc.paymentTerms")],
    ["#section-7", t("legal.terms.toc.serviceAvailability")],
    ["#section-8", t("legal.terms.toc.limitationOfLiability")],
    ["#section-9", t("legal.terms.toc.termination")],
    ["#section-10", t("legal.terms.toc.changesToTerms")],
    ["#section-11", t("legal.terms.toc.governingLaw")],
    ["#section-12", t("legal.terms.toc.contact")],
  ];

  return (
    <div className="legal-page">
      {/* Sticky header */}
      <div style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "var(--bg-surface)",
        borderBottom: "1px solid var(--border)",
        padding: "12px 24px",
        display: "flex",
        alignItems: "center",
        gap: "16px",
      }}>
        <Link to="/" style={{ textDecoration: "none", color: "var(--text-secondary)", fontSize: "14px", display: "flex", alignItems: "center", gap: "6px" }}>
          {"\u2190"} {t("legal.backToHome")}
        </Link>
        <span style={{ color: "var(--border)", fontSize: "14px" }}>|</span>
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>{t("legal.terms.pageTitle")}</span>
      </div>

      <div className="legal-container">
        <div className="legal-header">
          <Link to="/" style={{ textDecoration: "none" }}>
            <div className="auth-logo">QualiPulse</div>
          </Link>
          <h1 className="auth-title">{t("legal.terms.pageTitle")}</h1>
        </div>

        {/* Table of contents */}
        <nav style={{
          background: "var(--bg-sunken)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "20px 24px",
          marginBottom: "32px",
        }}>
          <p style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>{t("legal.contents")}</p>
          <ol style={{ margin: 0, padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: "6px" }}>
            {tocItems.map(([href, label]) => (
              <li key={href}>
                <a href={href} style={{ fontSize: "14px", color: "var(--primary)", textDecoration: "none" }}
                  onMouseEnter={(e) => { (e.target as HTMLElement).style.textDecoration = "underline"; }}
                  onMouseLeave={(e) => { (e.target as HTMLElement).style.textDecoration = "none"; }}
                >{label}</a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="legal-content">
          {isFR ? <TermsContentFR /> : <TermsContentEN />}
        </div>

        <p className="legal-updated">{t("legal.lastUpdated")}</p>
        <div className="legal-back">
          <Link to="/">{t("legal.backToHome")}</Link>
        </div>
      </div>
    </div>
  );
}
