import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

function PrivacyContentEN() {
  return (
    <>
      <h2 id="section-1" style={{ scrollMarginTop: "80px" }}>1. Introduction</h2>
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

      <h2 id="section-2" style={{ scrollMarginTop: "80px" }}>2. Data Controller</h2>
      <p>
        QualiPulse acts as a data processor on behalf of researchers who use the platform.
        Researchers are the data controllers for participant data collected through their
        interviews. For data related to researcher accounts and platform usage, QualiPulse
        acts as the data controller.
      </p>
      <p>
        Contact: <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>
      </p>

      <h2 id="section-3" style={{ scrollMarginTop: "80px" }}>3. Data We Collect</h2>
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

      <h2 id="section-4" style={{ scrollMarginTop: "80px" }}>4. How We Use Your Data</h2>
      <p>We process personal data for the following purposes:</p>
      <ul>
        <li><strong>Service delivery:</strong> To operate the platform, conduct AI-powered interviews, generate transcripts, and produce analysis reports.</li>
        <li><strong>Account management:</strong> To authenticate users, manage subscriptions, and send service-related communications.</li>
        <li><strong>Security:</strong> To detect and prevent fraud, abuse, and unauthorised access.</li>
        <li><strong>Service improvement:</strong> To monitor performance, fix bugs, and improve the user experience. We do not use your research data to train AI models.</li>
      </ul>

      <h2 id="section-5" style={{ scrollMarginTop: "80px" }}>5. Legal Basis for Processing</h2>
      <p>We process personal data under the following legal bases (GDPR Article 6):</p>
      <ul>
        <li><strong>Contract performance:</strong> Processing necessary to provide the Service you have subscribed to.</li>
        <li><strong>Legitimate interest:</strong> Security monitoring, fraud prevention, and service improvement.</li>
        <li><strong>Consent:</strong> Interview participants provide consent before beginning an interview. Researchers are responsible for ensuring appropriate consent mechanisms.</li>
        <li><strong>Legal obligation:</strong> Where we are required to process data to comply with applicable laws.</li>
      </ul>

      <h2 id="section-6" style={{ scrollMarginTop: "80px" }}>6. Third-Party Processors</h2>
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

      <h2 id="section-7" style={{ scrollMarginTop: "80px" }}>7. Data Storage and Security</h2>
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

      <h2 id="section-8" style={{ scrollMarginTop: "80px" }}>8. Data Retention</h2>
      <ul>
        <li><strong>Account data:</strong> Retained for the duration of your account plus 30 days after deletion to allow data export.</li>
        <li><strong>Interview data:</strong> Retained as long as the associated project exists. Researchers can delete projects and participant data at any time.</li>
        <li><strong>Audio recordings:</strong> Retained as long as the associated interview exists. Deleted when the participant or project is deleted.</li>
        <li><strong>Technical logs:</strong> Retained for up to 90 days for security and debugging purposes.</li>
      </ul>

      <h2 id="section-9" style={{ scrollMarginTop: "80px" }}>9. Your Rights</h2>
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

      <h2 id="section-10" style={{ scrollMarginTop: "80px" }}>10. Cookies</h2>
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

      <h2 id="section-11" style={{ scrollMarginTop: "80px" }}>11. Children's Privacy</h2>
      <p>
        The Service is not directed at individuals under the age of 18. We do not knowingly
        collect personal data from children. If you believe a child has provided us with
        personal data, please contact us and we will delete it.
      </p>

      <h2 id="section-12" style={{ scrollMarginTop: "80px" }}>12. Changes to This Policy</h2>
      <p>
        We may update this privacy policy from time to time. We will notify you of material
        changes via email or through the Service at least 30 days before they take effect.
        The "Last updated" date at the bottom of this page indicates when the policy was last
        revised.
      </p>

      <h2 id="section-13" style={{ scrollMarginTop: "80px" }}>13. Contact and Complaints</h2>
      <p>
        For any questions or concerns about this privacy policy or our data practices, contact
        us at <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>.
      </p>
      <p>
        If you are not satisfied with our response, you have the right to lodge a complaint
        with your local data protection supervisory authority.
      </p>
    </>
  );
}

function PrivacyContentFR() {
  return (
    <>
      <h2 id="section-1" style={{ scrollMarginTop: "80px" }}>1. Introduction</h2>
      <p>
        QualiPulse ({"\u00ab\u00a0"}nous{"\u00a0\u00bb"}, {"\u00ab\u00a0"}notre{"\u00a0\u00bb"}) s{"\u2019"}engage {"\u00e0"} prot{"\u00e9"}ger votre vie priv{"\u00e9"}e et {"\u00e0"} se
        conformer au R{"\u00e8"}glement G{"\u00e9"}n{"\u00e9"}ral sur la Protection des Donn{"\u00e9"}es (RGPD, R{"\u00e8"}glement (UE)
        2016/679) ainsi qu{"\u2019"}aux autres lois applicables en mati{"\u00e8"}re de protection des donn{"\u00e9"}es.
        La pr{"\u00e9"}sente politique explique quelles donn{"\u00e9"}es personnelles nous collectons, comment nous
        les utilisons et quels sont vos droits concernant ces donn{"\u00e9"}es.
      </p>
      <p>
        Cette politique s{"\u2019"}applique {"\u00e0"} tous les utilisateurs de la plateforme QualiPulse, y compris
        les chercheurs (titulaires de comptes) et les participants aux entretiens.
      </p>

      <h2 id="section-2" style={{ scrollMarginTop: "80px" }}>2. Responsable du traitement</h2>
      <p>
        QualiPulse agit en qualit{"\u00e9"} de sous-traitant (au sens de l{"\u2019"}article 28 du RGPD) pour le
        compte des chercheurs qui utilisent la plateforme. Les chercheurs sont les responsables
        du traitement des donn{"\u00e9"}es des participants collect{"\u00e9"}es lors de leurs entretiens. Pour les
        donn{"\u00e9"}es relatives aux comptes chercheurs et {"\u00e0"} l{"\u2019"}utilisation de la plateforme, QualiPulse
        agit en qualit{"\u00e9"} de responsable du traitement.
      </p>
      <p>
        Contact{"\u00a0"}: <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>
      </p>

      <h2 id="section-3" style={{ scrollMarginTop: "80px" }}>3. Donn{"\u00e9"}es que nous collectons</h2>
      <p>Nous collectons les cat{"\u00e9"}gories de donn{"\u00e9"}es personnelles suivantes{"\u00a0"}:</p>

      <p><strong>Donn{"\u00e9"}es de compte chercheur{"\u00a0"}:</strong></p>
      <ul>
        <li>Nom ou raison sociale, adresse e-mail et mot de passe hash{"\u00e9"}</li>
        <li>Informations d{"\u2019"}abonnement et de facturation (trait{"\u00e9"}es par Stripe)</li>
        <li>Projets de recherche, guides d{"\u2019"}entretien et donn{"\u00e9"}es d{"\u2019"}analyse</li>
      </ul>

      <p><strong>Donn{"\u00e9"}es des participants aux entretiens (collect{"\u00e9"}es pour le compte des chercheurs){"\u00a0"}:</strong></p>
      <ul>
        <li>Nom d{"\u2019"}affichage, e-mail, profession, tranche d{"\u2019"}{"\u00e2"}ge et pays (tous facultatifs, fournis par le participant)</li>
        <li>Enregistrements audio des r{"\u00e9"}ponses aux entretiens</li>
        <li>Transcriptions g{"\u00e9"}n{"\u00e9"}r{"\u00e9"}es {"\u00e0"} partir des enregistrements audio</li>
        <li>R{"\u00e9"}ponses aux questions de pr{"\u00e9"}s{"\u00e9"}lection</li>
      </ul>

      <p><strong>Donn{"\u00e9"}es techniques{"\u00a0"}:</strong></p>
      <ul>
        <li>Adresse IP, type de navigateur et informations sur l{"\u2019"}appareil (pour la s{"\u00e9"}curit{"\u00e9"} et le fonctionnement du service)</li>
        <li>Journaux d{"\u2019"}utilisation et rapports d{"\u2019"}erreurs</li>
      </ul>

      <h2 id="section-4" style={{ scrollMarginTop: "80px" }}>4. Utilisation de vos donn{"\u00e9"}es</h2>
      <p>Nous traitons les donn{"\u00e9"}es personnelles aux fins suivantes{"\u00a0"}:</p>
      <ul>
        <li><strong>Fourniture du service{"\u00a0"}:</strong> Exploiter la plateforme, mener des entretiens assist{"\u00e9"}s par IA, g{"\u00e9"}n{"\u00e9"}rer des transcriptions et produire des rapports d{"\u2019"}analyse.</li>
        <li><strong>Gestion des comptes{"\u00a0"}:</strong> Authentifier les utilisateurs, g{"\u00e9"}rer les abonnements et envoyer des communications li{"\u00e9"}es au service.</li>
        <li><strong>S{"\u00e9"}curit{"\u00e9"}{"\u00a0"}:</strong> D{"\u00e9"}tecter et pr{"\u00e9"}venir la fraude, les abus et les acc{"\u00e8"}s non autoris{"\u00e9"}s.</li>
        <li><strong>Am{"\u00e9"}lioration du service{"\u00a0"}:</strong> Surveiller les performances, corriger les erreurs et am{"\u00e9"}liorer l{"\u2019"}exp{"\u00e9"}rience utilisateur. Nous n{"\u2019"}utilisons pas vos donn{"\u00e9"}es de recherche pour entra{"\u00ee"}ner des mod{"\u00e8"}les d{"\u2019"}IA.</li>
      </ul>

      <h2 id="section-5" style={{ scrollMarginTop: "80px" }}>5. Base juridique du traitement</h2>
      <p>Nous traitons les donn{"\u00e9"}es personnelles sur les bases juridiques suivantes (article 6 du RGPD){"\u00a0"}:</p>
      <ul>
        <li><strong>Ex{"\u00e9"}cution du contrat{"\u00a0"}:</strong> Traitement n{"\u00e9"}cessaire {"\u00e0"} la fourniture du Service auquel vous avez souscrit.</li>
        <li><strong>Int{"\u00e9"}r{"\u00ea"}t l{"\u00e9"}gitime{"\u00a0"}:</strong> Surveillance de la s{"\u00e9"}curit{"\u00e9"}, pr{"\u00e9"}vention de la fraude et am{"\u00e9"}lioration du service.</li>
        <li><strong>Consentement{"\u00a0"}:</strong> Les participants aux entretiens donnent leur consentement avant de commencer un entretien. Les chercheurs sont responsables de la mise en place de m{"\u00e9"}canismes de consentement appropri{"\u00e9"}s.</li>
        <li><strong>Obligation l{"\u00e9"}gale{"\u00a0"}:</strong> Lorsque nous sommes tenus de traiter des donn{"\u00e9"}es pour nous conformer aux lois applicables.</li>
      </ul>

      <h2 id="section-6" style={{ scrollMarginTop: "80px" }}>6. Sous-traitants tiers</h2>
      <p>
        Nous faisons appel aux services tiers suivants pour exploiter la plateforme. Chacun
        traite les donn{"\u00e9"}es dans le cadre d{"\u2019"}un accord de traitement des donn{"\u00e9"}es (DPA){"\u00a0"}:
      </p>
      <ul>
        <li><strong>OpenAI</strong> ({"\u00c9"}tats-Unis) — Transcription vocale (Whisper) et g{"\u00e9"}n{"\u00e9"}ration audio par synth{"\u00e8"}se vocale. Les donn{"\u00e9"}es audio sont envoy{"\u00e9"}es pour traitement et ne sont pas conserv{"\u00e9"}es par OpenAI {"\u00e0"} des fins d{"\u2019"}entra{"\u00ee"}nement.</li>
        <li><strong>Anthropic</strong> ({"\u00c9"}tats-Unis) — Orchestration et analyse d{"\u2019"}entretiens par IA (Claude). Les donn{"\u00e9"}es de transcription sont envoy{"\u00e9"}es pour traitement et ne sont pas utilis{"\u00e9"}es pour entra{"\u00ee"}ner les mod{"\u00e8"}les d{"\u2019"}Anthropic.</li>
        <li><strong>SendGrid</strong> ({"\u00c9"}tats-Unis) — Envoi d{"\u2019"}e-mails transactionnels (v{"\u00e9"}rification, notifications).</li>
        <li><strong>Stripe</strong> ({"\u00c9"}tats-Unis) — Traitement des paiements. Nous ne stockons pas directement les donn{"\u00e9"}es de carte bancaire.</li>
        <li><strong>Google Cloud Platform</strong> (UE - Belgique) — H{"\u00e9"}bergement et calcul informatique.</li>
        <li><strong>Cloudflare</strong> (UE) — Stockage des fichiers audio (R2).</li>
        <li><strong>Neon</strong> (UE - Francfort) — H{"\u00e9"}bergement de la base de donn{"\u00e9"}es PostgreSQL.</li>
        <li><strong>Sentry</strong> (optionnel) — Suivi des erreurs et monitoring.</li>
      </ul>
      <p>
        Lorsque des donn{"\u00e9"}es sont transf{"\u00e9"}r{"\u00e9"}es vers des sous-traitants situ{"\u00e9"}s en dehors de
        l{"\u2019"}UE/EEE, nous veillons {"\u00e0"} ce que des garanties appropri{"\u00e9"}es soient en place, telles que
        les Clauses Contractuelles Types (CCT) ou le Cadre de Protection des Donn{"\u00e9"}es UE-{"\u00c9"}tats-Unis.
      </p>

      <h2 id="section-7" style={{ scrollMarginTop: "80px" }}>7. Stockage et s{"\u00e9"}curit{"\u00e9"} des donn{"\u00e9"}es</h2>
      <p>
        Vos donn{"\u00e9"}es sont stock{"\u00e9"}es sur des serveurs situ{"\u00e9"}s dans l{"\u2019"}Union europ{"\u00e9"}enne (Google Cloud
        Platform, Belgique{"\u00a0"}; Neon PostgreSQL, Francfort). Les fichiers audio sont stock{"\u00e9"}s dans
        Cloudflare R2 avec chiffrement au repos.
      </p>
      <p>
        Nous mettons en {"\u0153"}uvre des mesures techniques et organisationnelles appropri{"\u00e9"}es pour
        prot{"\u00e9"}ger vos donn{"\u00e9"}es, notamment le chiffrement en transit (TLS), le hachage des mots de
        passe (bcrypt), les contr{"\u00f4"}les d{"\u2019"}acc{"\u00e8"}s et les audits de s{"\u00e9"}curit{"\u00e9"} r{"\u00e9"}guliers.
      </p>

      <h2 id="section-8" style={{ scrollMarginTop: "80px" }}>8. Conservation des donn{"\u00e9"}es</h2>
      <ul>
        <li><strong>Donn{"\u00e9"}es de compte{"\u00a0"}:</strong> Conserv{"\u00e9"}es pendant la dur{"\u00e9"}e de votre compte, plus 30 jours apr{"\u00e8"}s la suppression pour permettre l{"\u2019"}export des donn{"\u00e9"}es.</li>
        <li><strong>Donn{"\u00e9"}es d{"\u2019"}entretien{"\u00a0"}:</strong> Conserv{"\u00e9"}es tant que le projet associ{"\u00e9"} existe. Les chercheurs peuvent supprimer les projets et les donn{"\u00e9"}es des participants {"\u00e0"} tout moment.</li>
        <li><strong>Enregistrements audio{"\u00a0"}:</strong> Conserv{"\u00e9"}s tant que l{"\u2019"}entretien associ{"\u00e9"} existe. Supprim{"\u00e9"}s lors de la suppression du participant ou du projet.</li>
        <li><strong>Journaux techniques{"\u00a0"}:</strong> Conserv{"\u00e9"}s jusqu{"\u2019"}{"\u00e0"} 90 jours {"\u00e0"} des fins de s{"\u00e9"}curit{"\u00e9"} et de d{"\u00e9"}bogage.</li>
      </ul>

      <h2 id="section-9" style={{ scrollMarginTop: "80px" }}>9. Vos droits</h2>
      <p>En vertu du RGPD, vous disposez des droits suivants{"\u00a0"}:</p>
      <ul>
        <li><strong>Droit d{"\u2019"}acc{"\u00e8"}s{"\u00a0"}:</strong> Demander une copie des donn{"\u00e9"}es personnelles que nous d{"\u00e9"}tenons {"\u00e0"} votre sujet.</li>
        <li><strong>Droit de rectification{"\u00a0"}:</strong> Demander la correction de donn{"\u00e9"}es personnelles inexactes.</li>
        <li><strong>Droit {"\u00e0"} l{"\u2019"}effacement{"\u00a0"}:</strong> Demander la suppression de vos donn{"\u00e9"}es personnelles ({"\u00ab\u00a0"}droit {"\u00e0"} l{"\u2019"}oubli{"\u00a0\u00bb"}).</li>
        <li><strong>Droit {"\u00e0"} la portabilit{"\u00e9"}{"\u00a0"}:</strong> Recevoir vos donn{"\u00e9"}es dans un format structur{"\u00e9"} et lisible par machine (l{"\u2019"}export CSV est disponible pour les donn{"\u00e9"}es d{"\u2019"}entretien).</li>
        <li><strong>Droit {"\u00e0"} la limitation du traitement{"\u00a0"}:</strong> Demander que nous limitions le traitement de vos donn{"\u00e9"}es.</li>
        <li><strong>Droit d{"\u2019"}opposition{"\u00a0"}:</strong> Vous opposer au traitement fond{"\u00e9"} sur l{"\u2019"}int{"\u00e9"}r{"\u00ea"}t l{"\u00e9"}gitime.</li>
        <li><strong>Droit de retrait du consentement{"\u00a0"}:</strong> Lorsque le traitement est fond{"\u00e9"} sur le consentement, vous pouvez le retirer {"\u00e0"} tout moment.</li>
      </ul>
      <p>
        Pour exercer l{"\u2019"}un de ces droits, contactez-nous {"\u00e0"}{" "}
        <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>. Nous vous
        r{"\u00e9"}pondrons dans un d{"\u00e9"}lai de 30 jours.
      </p>
      <p>
        <strong>Participants aux entretiens{"\u00a0"}:</strong> Si vous avez particip{"\u00e9"} {"\u00e0"} un entretien et
        souhaitez exercer vos droits, vous pouvez nous contacter directement ou vous adresser
        au chercheur qui a cr{"\u00e9"}{"\u00e9"} l{"\u2019"}entretien. Les chercheurs peuvent supprimer les donn{"\u00e9"}es des
        participants via la plateforme.
      </p>

      <h2 id="section-10" style={{ scrollMarginTop: "80px" }}>10. Cookies</h2>
      <p>
        QualiPulse utilise uniquement des cookies essentiels et le stockage local n{"\u00e9"}cessaires
        au fonctionnement du Service{"\u00a0"}:
      </p>
      <ul>
        <li><strong>Jetons d{"\u2019"}authentification{"\u00a0"}:</strong> Stock{"\u00e9"}s dans le stockage local pour maintenir votre session de connexion.</li>
        <li><strong>Donn{"\u00e9"}es de session{"\u00a0"}:</strong> Stock{"\u00e9"}es dans le stockage de session pour permettre la reprise d{"\u2019"}un entretien.</li>
      </ul>
      <p>
        Nous n{"\u2019"}utilisons pas de cookies de suivi, de cookies publicitaires ni de cookies
        d{"\u2019"}analyse tiers.
      </p>

      <h2 id="section-11" style={{ scrollMarginTop: "80px" }}>11. Protection des mineurs</h2>
      <p>
        Le Service ne s{"\u2019"}adresse pas aux personnes de moins de 18 ans. Nous ne collectons pas
        sciemment de donn{"\u00e9"}es personnelles aupr{"\u00e8"}s de mineurs. Si vous pensez qu{"\u2019"}un mineur nous a
        communiqu{"\u00e9"} des donn{"\u00e9"}es personnelles, veuillez nous contacter et nous les supprimerons.
      </p>

      <h2 id="section-12" style={{ scrollMarginTop: "80px" }}>12. Modifications de cette politique</h2>
      <p>
        Nous pouvons mettre {"\u00e0"} jour la pr{"\u00e9"}sente politique de confidentialit{"\u00e9"} de temps {"\u00e0"} autre.
        Nous vous informerons de toute modification substantielle par e-mail ou via le Service
        au moins 30 jours avant son entr{"\u00e9"}e en vigueur. La date de {"\u00ab\u00a0"}derni{"\u00e8"}re mise {"\u00e0"} jour{"\u00a0\u00bb"} en
        bas de cette page indique la derni{"\u00e8"}re r{"\u00e9"}vision de la politique.
      </p>

      <h2 id="section-13" style={{ scrollMarginTop: "80px" }}>13. Contact et r{"\u00e9"}clamations</h2>
      <p>
        Pour toute question ou pr{"\u00e9"}occupation concernant la pr{"\u00e9"}sente politique de confidentialit{"\u00e9"}
        ou nos pratiques en mati{"\u00e8"}re de donn{"\u00e9"}es, contactez-nous {"\u00e0"}{" "}
        <a href="mailto:privacy@qualipulse.com">privacy@qualipulse.com</a>.
      </p>
      <p>
        Si vous n{"\u2019"}{"\u00ea"}tes pas satisfait de notre r{"\u00e9"}ponse, vous avez le droit de d{"\u00e9"}poser une
        r{"\u00e9"}clamation aupr{"\u00e8"}s de l{"\u2019"}autorit{"\u00e9"} de contr{"\u00f4"}le comp{"\u00e9"}tente en mati{"\u00e8"}re de protection des
        donn{"\u00e9"}es (en France{"\u00a0"}: la CNIL).
      </p>
    </>
  );
}

export default function Privacy() {
  const { t, i18n } = useTranslation();
  const isFR = i18n.language?.startsWith("fr");

  const tocItems: [string, string][] = [
    ["#section-1", t("legal.privacy.toc.introduction")],
    ["#section-2", t("legal.privacy.toc.dataController")],
    ["#section-3", t("legal.privacy.toc.dataWeCollect")],
    ["#section-4", t("legal.privacy.toc.howWeUseYourData")],
    ["#section-5", t("legal.privacy.toc.legalBasis")],
    ["#section-6", t("legal.privacy.toc.thirdPartyProcessors")],
    ["#section-7", t("legal.privacy.toc.dataStorageAndSecurity")],
    ["#section-8", t("legal.privacy.toc.dataRetention")],
    ["#section-9", t("legal.privacy.toc.yourRights")],
    ["#section-10", t("legal.privacy.toc.cookies")],
    ["#section-11", t("legal.privacy.toc.childrensPrivacy")],
    ["#section-12", t("legal.privacy.toc.changesToPolicy")],
    ["#section-13", t("legal.privacy.toc.contactAndComplaints")],
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
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>{t("legal.privacy.pageTitle")}</span>
      </div>

      <div className="legal-container">
        <div className="legal-header">
          <Link to="/" style={{ textDecoration: "none" }}>
            <div className="auth-logo">QualiPulse</div>
          </Link>
          <h1 className="auth-title">{t("legal.privacy.pageTitle")}</h1>
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
          {isFR ? <PrivacyContentFR /> : <PrivacyContentEN />}
        </div>

        <p className="legal-updated">{t("legal.lastUpdated")}</p>
        <div className="legal-back">
          <Link to="/">{t("legal.backToHome")}</Link>
        </div>
      </div>
    </div>
  );
}
