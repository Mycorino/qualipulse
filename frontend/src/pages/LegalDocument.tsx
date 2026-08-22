import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";

type Section = {
  id: string;
  title: string;
  body: string[];
  bullets?: string[];
};

type LegalDoc = {
  title: string;
  intro: string;
  sections: Section[];
};

const docs = {
  dpa: {
    en: {
      title: "Data Processing Agreement",
      intro:
        "This Data Processing Agreement forms part of the agreement between QualiPulse and each customer that uses the Service to process personal data on behalf of its organisation.",
      sections: [
        {
          id: "roles",
          title: "1. Roles of the parties",
          body: [
            "For participant interview data, the customer is the controller and QualiPulse is the processor. For account, billing, security, support, and service analytics data, QualiPulse acts as an independent controller.",
          ],
        },
        {
          id: "processing",
          title: "2. Processing instructions",
          body: [
            "QualiPulse processes customer personal data only to provide, secure, support, and maintain the Service, or as otherwise documented in the customer's configuration or written instructions.",
          ],
          bullets: [
            "Subject matter: AI-moderated research interviews, transcription, analysis, storage, export, and related support.",
            "Duration: the term of the customer account plus the deletion and retention periods described in the Retention Policy.",
            "Data subjects: customer users, invited participants, and research panel contacts where enabled.",
            "Data categories: identifiers, contact details, demographics supplied by participants, audio, transcripts, research responses, project metadata, and technical logs.",
          ],
        },
        {
          id: "security",
          title: "3. Security measures",
          body: [
            "QualiPulse maintains appropriate technical and organisational measures designed to protect personal data against accidental or unlawful destruction, loss, alteration, unauthorised disclosure, or access.",
          ],
          bullets: [
            "Encryption in transit using TLS.",
            "Password hashing for account credentials.",
            "Role-based access controls for customer workspaces.",
            "Production data access limited to authorised personnel with a support or security need.",
            "Logical separation of customer workspaces.",
            "Security and application logs for abuse detection and incident investigation.",
          ],
        },
        {
          id: "subprocessors",
          title: "4. Subprocessors",
          body: [
            "Customer authorises QualiPulse to use subprocessors listed on the Subprocessors page. QualiPulse remains responsible for subprocessors' performance of data protection obligations and will use contractual protections appropriate to the processing.",
          ],
        },
        {
          id: "assistance",
          title: "5. Assistance and data subject requests",
          body: [
            "QualiPulse will provide reasonable assistance to help customers respond to data subject requests, security obligations, DPIAs, and regulator enquiries, taking into account the nature of the processing and information available to QualiPulse.",
          ],
        },
        {
          id: "breach",
          title: "6. Security incidents",
          body: [
            "QualiPulse will notify affected customers without undue delay after becoming aware of a personal data breach involving customer personal data and will provide information reasonably available to support required notices.",
          ],
        },
        {
          id: "transfers",
          title: "7. International transfers",
          body: [
            "Where personal data is transferred outside the EEA, UK, or Switzerland, QualiPulse will rely on appropriate safeguards such as Standard Contractual Clauses, adequacy decisions, or other lawful transfer mechanisms.",
          ],
        },
        {
          id: "deletion",
          title: "8. Return and deletion",
          body: [
            "On termination or written request, QualiPulse will delete or return customer personal data within a reasonable period unless retention is required by law, security, backup integrity, dispute resolution, or legitimate business recordkeeping.",
          ],
        },
      ],
    },
    fr: {
      title: "Accord de traitement des données",
      intro:
        "Cet accord de traitement des données fait partie de l'accord entre QualiPulse et chaque client qui utilise le Service pour traiter des données personnelles pour le compte de son organisation.",
      sections: [
        {
          id: "roles",
          title: "1. Rôles des parties",
          body: [
            "Pour les données d'entretien participant, le client est responsable du traitement et QualiPulse est sous-traitant. Pour les données de compte, facturation, sécurité, support et analytics du service, QualiPulse agit comme responsable du traitement indépendant.",
          ],
        },
        {
          id: "processing",
          title: "2. Instructions de traitement",
          body: [
            "QualiPulse traite les données personnelles client uniquement pour fournir, sécuriser, supporter et maintenir le Service, ou selon la configuration du client ou ses instructions écrites.",
          ],
          bullets: [
            "Objet: entretiens de recherche modérés par IA, transcription, analyse, stockage, export et support associé.",
            "Durée: durée du compte client plus les périodes de suppression et conservation décrites dans la politique de conservation.",
            "Personnes concernées: utilisateurs client, participants invités et contacts panel lorsque cette fonctionnalité est activée.",
            "Catégories: identifiants, coordonnées, données démographiques fournies, audio, transcriptions, réponses de recherche, métadonnées projet et journaux techniques.",
          ],
        },
        {
          id: "security",
          title: "3. Mesures de sécurité",
          body: [
            "QualiPulse maintient des mesures techniques et organisationnelles appropriées pour protéger les données personnelles contre destruction, perte, altération, divulgation ou accès non autorisé.",
          ],
          bullets: [
            "Chiffrement en transit via TLS.",
            "Hachage des mots de passe.",
            "Contrôles d'accès par rôle pour les espaces client.",
            "Accès aux données de production limité au personnel autorisé pour support ou sécurité.",
            "Séparation logique des espaces client.",
            "Journaux de sécurité et d'application pour détecter les abus et enquêter sur les incidents.",
          ],
        },
        {
          id: "subprocessors",
          title: "4. Sous-traitants ultérieurs",
          body: [
            "Le client autorise QualiPulse à utiliser les sous-traitants listés sur la page Sous-traitants. QualiPulse reste responsable de l'exécution de leurs obligations de protection des données et utilise des protections contractuelles adaptées.",
          ],
        },
        {
          id: "assistance",
          title: "5. Assistance et demandes des personnes",
          body: [
            "QualiPulse fournit une assistance raisonnable pour aider les clients à répondre aux demandes des personnes, obligations de sécurité, AIPD et demandes des autorités, selon la nature du traitement et les informations disponibles.",
          ],
        },
        {
          id: "breach",
          title: "6. Incidents de sécurité",
          body: [
            "QualiPulse notifiera les clients affectés sans retard injustifié après avoir pris connaissance d'une violation de données personnelles impliquant des données client.",
          ],
        },
        {
          id: "transfers",
          title: "7. Transferts internationaux",
          body: [
            "Lorsque des données sont transférées hors EEE, Royaume-Uni ou Suisse, QualiPulse s'appuie sur des garanties appropriées comme les Clauses Contractuelles Types, décisions d'adéquation ou autres mécanismes licites.",
          ],
        },
        {
          id: "deletion",
          title: "8. Retour et suppression",
          body: [
            "A la résiliation ou sur demande écrite, QualiPulse supprime ou retourne les données personnelles client dans un délai raisonnable, sauf conservation requise par la loi, la sécurité, l'intégrité des sauvegardes, un litige ou les registres commerciaux légitimes.",
          ],
        },
      ],
    },
  },
  subprocessors: {
    en: {
      title: "Subprocessors",
      intro:
        "QualiPulse uses the following vendors to provide, secure, and operate the Service. Availability and location may depend on the customer's configuration and production environment.",
      sections: [
        {
          id: "list",
          title: "Current subprocessors",
          body: [],
          bullets: [
            "OpenAI - speech-to-text transcription and text-to-speech processing.",
            "Anthropic - AI interview orchestration, research copilot, and analysis.",
            "Google Cloud Platform - application hosting and compute.",
            "Neon - PostgreSQL database hosting.",
            "Cloudflare R2 - audio and file storage.",
            "Stripe - payment processing and billing records.",
            "SendGrid - transactional email delivery.",
            "Sentry - optional error monitoring and diagnostics.",
          ],
        },
        {
          id: "notice",
          title: "Notice of changes",
          body: [
            "QualiPulse may update subprocessors as the Service evolves. Material changes will be reflected on this page and, where required by contract or law, notified to customers before the new subprocessor is used for customer personal data.",
          ],
        },
        {
          id: "transfers",
          title: "Transfers and safeguards",
          body: [
            "Where a subprocessor processes personal data outside the EEA, UK, or Switzerland, QualiPulse relies on appropriate transfer safeguards such as Standard Contractual Clauses, adequacy decisions, or equivalent mechanisms.",
          ],
        },
      ],
    },
    fr: {
      title: "Sous-traitants",
      intro:
        "QualiPulse utilise les fournisseurs suivants pour fournir, sécuriser et exploiter le Service. La disponibilité et la localisation peuvent dépendre de la configuration client et de l'environnement de production.",
      sections: [
        {
          id: "list",
          title: "Sous-traitants actuels",
          body: [],
          bullets: [
            "OpenAI - transcription vocale et synthèse vocale.",
            "Anthropic - orchestration d'entretiens IA, copilote de recherche et analyse.",
            "Google Cloud Platform - hébergement applicatif et calcul.",
            "Neon - hébergement de base de données PostgreSQL.",
            "Cloudflare R2 - stockage audio et fichiers.",
            "Stripe - paiement et facturation.",
            "SendGrid - emails transactionnels.",
            "Sentry - monitoring optionnel des erreurs et diagnostics.",
          ],
        },
        {
          id: "notice",
          title: "Notification des changements",
          body: [
            "QualiPulse peut mettre à jour ses sous-traitants avec l'évolution du Service. Les changements matériels seront reflétés sur cette page et, lorsque le contrat ou la loi l'exige, notifiés aux clients avant utilisation pour les données personnelles client.",
          ],
        },
        {
          id: "transfers",
          title: "Transferts et garanties",
          body: [
            "Lorsqu'un sous-traitant traite des données hors EEE, Royaume-Uni ou Suisse, QualiPulse s'appuie sur des garanties appropriées comme les Clauses Contractuelles Types, décisions d'adéquation ou mécanismes équivalents.",
          ],
        },
      ],
    },
  },
  "participant-notice": {
    en: {
      title: "Participant Interview Notice",
      intro:
        "This notice explains what happens when you take part in a QualiPulse-powered research interview. The organisation that shared the interview link is responsible for the study.",
      sections: [
        {
          id: "who",
          title: "1. Who is running the study",
          body: [
            "The researcher or organisation that invited you decides the purpose of the study, the interview questions, and how your responses will be used. QualiPulse provides the interview technology on their behalf.",
          ],
        },
        {
          id: "ai",
          title: "2. AI-moderated interview",
          body: [
            "The interview is conducted by an AI moderator. It follows the interview guide and may ask follow-up questions based on your answers. You can stop participating at any time by closing the page.",
          ],
        },
        {
          id: "data",
          title: "3. Data collected",
          body: [
            "Your voice responses are recorded, transcribed, and analysed for research purposes. You may also be asked optional profile or screening questions such as role, age range, country, or email for interview continuation.",
          ],
        },
        {
          id: "use",
          title: "4. How responses are used",
          body: [
            "Researchers use responses to understand themes, quotes, needs, pain points, and product or service feedback. QualiPulse does not sell participant data and does not use customer research data to train AI models.",
          ],
        },
        {
          id: "rights",
          title: "5. Your rights",
          body: [
            "You may contact the researcher that shared the interview or privacy@qualipulse.com to request access, deletion, correction, restriction, objection, or withdrawal of consent where applicable.",
          ],
        },
      ],
    },
    fr: {
      title: "Notice participant",
      intro:
        "Cette notice explique ce qui se passe lorsque vous participez à un entretien de recherche propulsé par QualiPulse. L'organisation qui a partagé le lien est responsable de l'étude.",
      sections: [
        {
          id: "who",
          title: "1. Qui mène l'étude",
          body: [
            "Le chercheur ou l'organisation qui vous invite décide de l'objectif de l'étude, des questions et de l'utilisation des réponses. QualiPulse fournit la technologie d'entretien pour son compte.",
          ],
        },
        {
          id: "ai",
          title: "2. Entretien modéré par IA",
          body: [
            "L'entretien est conduit par un modérateur IA. Il suit le guide d'entretien et peut poser des questions de relance selon vos réponses. Vous pouvez arrêter à tout moment en fermant la page.",
          ],
        },
        {
          id: "data",
          title: "3. Données collectées",
          body: [
            "Vos réponses vocales sont enregistrées, transcrites et analysées à des fins de recherche. Des questions optionnelles de profil ou sélection peuvent aussi être posées, comme rôle, tranche d'âge, pays ou email pour reprendre l'entretien.",
          ],
        },
        {
          id: "use",
          title: "4. Utilisation des réponses",
          body: [
            "Les chercheurs utilisent les réponses pour comprendre thèmes, citations, besoins, douleurs et retours produit ou service. QualiPulse ne vend pas les données participant et n'utilise pas les données de recherche client pour entraîner des modèles IA.",
          ],
        },
        {
          id: "rights",
          title: "5. Vos droits",
          body: [
            "Vous pouvez contacter le chercheur qui a partagé l'entretien ou privacy@qualipulse.com pour demander accès, suppression, correction, limitation, opposition ou retrait du consentement lorsque applicable.",
          ],
        },
      ],
    },
  },
  "ai-use-policy": {
    en: {
      title: "AI Use Policy",
      intro:
        "This policy explains how QualiPulse uses AI and which uses are not allowed without prior written approval.",
      sections: [
        {
          id: "ai-use",
          title: "1. How AI is used",
          body: [
            "QualiPulse uses AI to draft research guides, conduct interview follow-ups, transcribe or transform content, summarise interviews, identify themes, generate research memos, and assist researchers.",
          ],
        },
        {
          id: "human",
          title: "2. Human responsibility",
          body: [
            "AI outputs are research aids, not final decisions. Customers remain responsible for reviewing study design, participant notices, generated questions, analysis, and any decisions made from the research.",
          ],
        },
        {
          id: "prohibited",
          title: "3. Prohibited or restricted uses",
          body: ["Customers must not use QualiPulse for:"],
          bullets: [
            "Hiring, promotion, termination, worker monitoring, or employment eligibility decisions.",
            "Credit, insurance, housing, education access, healthcare diagnosis, legal eligibility, or government benefit decisions.",
            "Biometric identification, speaker identification, emotion recognition, or sensitive attribute inference.",
            "Research targeting children or vulnerable groups without appropriate safeguards and written approval.",
            "Collecting special category data unless the customer has a valid legal basis and configured safeguards.",
            "Deceptive, manipulative, unlawful, discriminatory, or surveillance purposes.",
          ],
        },
        {
          id: "disclosure",
          title: "4. Transparency",
          body: [
            "Participants must be told when they are interacting with an AI interviewer and that their responses may be recorded, transcribed, and analysed by AI.",
          ],
        },
      ],
    },
    fr: {
      title: "Politique d'utilisation de l'IA",
      intro:
        "Cette politique explique comment QualiPulse utilise l'IA et quels usages sont interdits sans approbation écrite préalable.",
      sections: [
        {
          id: "ai-use",
          title: "1. Utilisation de l'IA",
          body: [
            "QualiPulse utilise l'IA pour rédiger des guides de recherche, mener des relances d'entretien, transcrire ou transformer du contenu, résumer des entretiens, identifier des thèmes, générer des memos et assister les chercheurs.",
          ],
        },
        {
          id: "human",
          title: "2. Responsabilité humaine",
          body: [
            "Les sorties IA sont des aides à la recherche, pas des décisions finales. Les clients restent responsables de relire conception d'étude, notices participant, questions générées, analyses et décisions prises à partir de la recherche.",
          ],
        },
        {
          id: "prohibited",
          title: "3. Usages interdits ou restreints",
          body: ["Les clients ne doivent pas utiliser QualiPulse pour:"],
          bullets: [
            "Recrutement, promotion, licenciement, surveillance des travailleurs ou décisions d'éligibilité a l'emploi.",
            "Credit, assurance, logement, accès à l'éducation, diagnostic médical, éligibilité juridique ou aides publiques.",
            "Identification biométrique, identification du locuteur, reconnaissance émotionnelle ou inference d'attributs sensibles.",
            "Recherche visant des enfants ou groupes vulnérables sans garanties appropriées et approbation écrite.",
            "Collecte de données sensibles sans base juridique valide et garanties configurées.",
            "Usages trompeurs, manipulateurs, illicites, discriminatoires ou de surveillance.",
          ],
        },
        {
          id: "disclosure",
          title: "4. Transparence",
          body: [
            "Les participants doivent être informés qu'ils interagissent avec un interviewer IA et que leurs réponses peuvent être enregistrées, transcrites et analysées par IA.",
          ],
        },
      ],
    },
  },
  "retention-policy": {
    en: {
      title: "Data Retention Policy",
      intro:
        "This policy summarises how long QualiPulse keeps different categories of data. Customers may configure shorter study retention by deleting projects, participants, or exports.",
      sections: [
        {
          id: "customer",
          title: "1. Customer account data",
          body: [
            "Account profile, workspace, authentication, and billing metadata are kept while the account is active and for a reasonable period after closure where needed for legal, tax, security, or dispute purposes.",
          ],
        },
        {
          id: "research",
          title: "2. Research project data",
          body: [
            "Interview guides, project metadata, participant records, transcripts, analysis, memos, tags, and reports are kept while the relevant project or workspace remains active, unless deleted earlier by the customer.",
          ],
        },
        {
          id: "audio",
          title: "3. Audio recordings",
          body: [
            "Audio recordings are retained while the associated interview exists and are deleted when the participant, interview, project, or workspace is deleted, subject to backup and security retention windows.",
          ],
        },
        {
          id: "logs",
          title: "4. Logs and security records",
          body: [
            "Application, security, usage, billing, and audit logs may be retained for security, fraud prevention, debugging, billing accuracy, legal compliance, and support.",
          ],
        },
        {
          id: "backups",
          title: "5. Backups",
          body: [
            "Deleted data may remain in encrypted backups for a limited period until backups rotate out. Backups are not used for ordinary production access and are restored only for resilience, security, or disaster recovery.",
          ],
        },
        {
          id: "deletion",
          title: "6. Deletion requests",
          body: [
            "Customers can delete project and participant data in the product. Participants can request deletion through the researcher or by contacting privacy@qualipulse.com so we can route the request appropriately.",
          ],
        },
      ],
    },
    fr: {
      title: "Politique de conservation des données",
      intro:
        "Cette politique résume combien de temps QualiPulse conserve les différentes catégories de données. Les clients peuvent appliquer une conservation plus courte en supprimant projets, participants ou exports.",
      sections: [
        {
          id: "customer",
          title: "1. Données de compte client",
          body: [
            "Les données de profil, workspace, authentification et facturation sont conservées tant que le compte est actif puis pendant une période raisonnable si nécessaire pour raisons légales, fiscales, sécurité ou litiges.",
          ],
        },
        {
          id: "research",
          title: "2. Données de projet de recherche",
          body: [
            "Guides d'entretien, métadonnées projet, participants, transcriptions, analyses, memos, tags et rapports sont conservés tant que le projet ou workspace reste actif, sauf suppression plus tôt par le client.",
          ],
        },
        {
          id: "audio",
          title: "3. Enregistrements audio",
          body: [
            "Les enregistrements audio sont conservés tant que l'entretien associé existe et sont supprimés lorsque le participant, entretien, projet ou workspace est supprimé, sous réserve des fenêtres de sauvegarde et sécurité.",
          ],
        },
        {
          id: "logs",
          title: "4. Journaux et registres de sécurité",
          body: [
            "Les journaux applicatifs, sécurité, usage, facturation et audit peuvent être conservés pour sécurité, prévention de fraude, debug, exactitude de facturation, conformité légale et support.",
          ],
        },
        {
          id: "backups",
          title: "5. Sauvegardes",
          body: [
            "Les données supprimées peuvent rester dans des sauvegardes chiffrées pendant une période limitée jusqu'à rotation. Les sauvegardes ne sont pas utilisées pour l'accès production ordinaire.",
          ],
        },
        {
          id: "deletion",
          title: "6. Demandes de suppression",
          body: [
            "Les clients peuvent supprimer données projet et participant dans le produit. Les participants peuvent demander la suppression via le chercheur ou privacy@qualipulse.com afin que nous routions la demande correctement.",
          ],
        },
      ],
    },
  },
} satisfies Record<string, Record<"en" | "fr", LegalDoc>>;

type DocKey = keyof typeof docs;

function resolveDoc(pathname: string): DocKey {
  const key = pathname.replace(/^\//, "") || "dpa";
  return key in docs ? (key as DocKey) : "dpa";
}

export default function LegalDocument() {
  const { t, i18n } = useTranslation();
  const { pathname } = useLocation();
  const docKey = resolveDoc(pathname);
  const lang = i18n.language?.startsWith("fr") ? "fr" : "en";
  const doc: LegalDoc = docs[docKey][lang];
  useHead({ title: `${doc.title} — QualiPulse` });

  return (
    <div className="legal-page">
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
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>{doc.title}</span>
      </div>

      <div className="legal-container">
        <div className="legal-header">
          <Link to="/" style={{ textDecoration: "none" }}>
            <div className="auth-logo">QualiPulse</div>
          </Link>
          <h1 className="auth-title">{doc.title}</h1>
          <p className="auth-subtitle" style={{ maxWidth: 720, margin: "8px auto 0" }}>
            {doc.intro}
          </p>
        </div>

        <nav style={{
          background: "var(--bg-sunken)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "20px 24px",
          marginBottom: "32px",
        }}>
          <p style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>
            {t("legal.contents")}
          </p>
          <ol style={{ margin: 0, padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: "6px" }}>
            {doc.sections.map((section) => (
              <li key={section.id}>
                <a href={`#${section.id}`} style={{ fontSize: "14px", color: "var(--primary)", textDecoration: "none" }}>
                  {section.title.replace(/^\d+\.\s*/, "")}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="legal-content">
          {doc.sections.map((section) => (
            <section key={section.id}>
              <h2 id={section.id} style={{ scrollMarginTop: "80px" }}>{section.title}</h2>
              {section.body.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
              {section.bullets && (
                <ul>
                  {section.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        <p className="legal-updated">{t("legal.lastUpdated")}</p>
        <div className="legal-back">
          <Link to="/terms">{lang === "fr" ? "Conditions" : "Terms"}</Link>
          {" · "}
          <Link to="/privacy">{lang === "fr" ? "Confidentialité" : "Privacy"}</Link>
          {" · "}
          <Link to="/">{t("legal.backToHome")}</Link>
        </div>
      </div>
    </div>
  );
}
