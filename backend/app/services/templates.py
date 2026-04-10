"""
Research project templates.

These are pre-built starting points for common qualitative research studies.
Users can pick a template in the project wizard to skip the blank-canvas
problem; the template pre-fills the objective, target audience, screening
questions, and a full interview guide that can then be customized.

Templates are intentionally defined in code (not the database) so they can be
version-controlled, internationalized via i18n in the frontend, and tweaked
without migrations.
"""

from __future__ import annotations

from typing import List, TypedDict


class TemplateQuestion(TypedDict):
    section_index: int
    section_title: str
    question_index: int
    main_question: str
    interview_notes: str
    desired_learning: str


class TemplateScreeningQuestion(TypedDict):
    question: str
    options: List[str]
    disqualifying_options: List[str]


class ProjectTemplate(TypedDict):
    id: str
    name: str
    category: str  # saas, ecommerce, product, marketing, research, startup
    icon: str  # emoji for UI
    description: str
    best_for: str  # short "who it's for" line
    duration_minutes: int
    research_objective: str
    target_audience: str
    learning_goals: List[str]
    screening_questions: List[TemplateScreeningQuestion]
    questions: List[TemplateQuestion]


TEMPLATES: List[ProjectTemplate] = [
    {
        "id": "customer-churn",
        "name": "Customer Churn Research",
        "category": "saas",
        "icon": "📉",
        "description": "Understand why paying customers are leaving. Dig into the switching moment, the triggers, and whether the product gap is fixable.",
        "best_for": "SaaS teams with rising churn or low retention",
        "duration_minutes": 20,
        "research_objective": "Understand the root causes of customer churn and identify the most actionable levers to improve retention.",
        "target_audience": "Former customers who cancelled in the last 90 days, across tiers and tenure (at least 1 month of usage before cancelling).",
        "learning_goals": [
            "What was the triggering moment that made them decide to cancel?",
            "Which specific product or service gaps contributed to the decision?",
            "What would have made them stay, if anything?",
        ],
        "screening_questions": [
            {
                "question": "When did you cancel your subscription?",
                "options": ["In the last 30 days", "1–3 months ago", "More than 3 months ago", "I haven't cancelled"],
                "disqualifying_options": ["More than 3 months ago", "I haven't cancelled"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "Context", "question_index": 0, "main_question": "Tell me a bit about your role and what you were using our product for.", "interview_notes": "Warm-up. Let them set context in their own words.", "desired_learning": "Baseline use case and role"},
            {"section_index": 0, "section_title": "Context", "question_index": 1, "main_question": "How did you originally hear about us and what made you sign up?", "interview_notes": "", "desired_learning": "Acquisition channel and original job-to-be-done"},
            {"section_index": 1, "section_title": "The switching moment", "question_index": 2, "main_question": "Can you walk me through the moment you decided to cancel? What happened that week?", "interview_notes": "Probe for the trigger event. Ask 'what happened next?' until you get the full story.", "desired_learning": "The specific triggering event"},
            {"section_index": 1, "section_title": "The switching moment", "question_index": 3, "main_question": "Were there any frustrations that had been building up before that moment?", "interview_notes": "", "desired_learning": "Long-term frustrations vs. acute triggers"},
            {"section_index": 2, "section_title": "Alternatives", "question_index": 4, "main_question": "What are you using instead now, if anything? How is it working out?", "interview_notes": "Don't lead. Let them name alternatives freely.", "desired_learning": "Competitive alternatives and their perceived advantages"},
            {"section_index": 2, "section_title": "Alternatives", "question_index": 5, "main_question": "What would have made you stay?", "interview_notes": "This is the money question — probe for specifics.", "desired_learning": "Actionable retention levers"},
        ],
    },
    {
        "id": "feature-validation",
        "name": "Feature Validation Research",
        "category": "saas",
        "icon": "🔬",
        "description": "Test whether a specific feature idea actually solves a real problem, before you commit engineering to it.",
        "best_for": "Product managers validating a hypothesis pre-build",
        "duration_minutes": 20,
        "research_objective": "Validate whether a proposed feature addresses a real customer pain point and understand what the ideal solution looks like from the user's perspective.",
        "target_audience": "Active users of the product who have experienced the problem space we're investigating in the last 30 days.",
        "learning_goals": [
            "How often and how painfully do users experience this problem today?",
            "What workarounds are they using, and how good are those workarounds?",
            "How would they describe the ideal solution in their own words?",
        ],
        "screening_questions": [
            {
                "question": "How often do you use our product?",
                "options": ["Multiple times per day", "A few times per week", "Less than weekly", "I've stopped using it"],
                "disqualifying_options": ["I've stopped using it"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "Current workflow", "question_index": 0, "main_question": "Walk me through the last time you [relevant task]. What did that look like?", "interview_notes": "Concrete, recent example. Not hypothetical.", "desired_learning": "Actual current workflow"},
            {"section_index": 0, "section_title": "Current workflow", "question_index": 1, "main_question": "Where does that workflow get frustrating or slow for you?", "interview_notes": "", "desired_learning": "Specific pain points"},
            {"section_index": 1, "section_title": "Workarounds", "question_index": 2, "main_question": "How do you deal with that today? Any workarounds or tools you use to make it easier?", "interview_notes": "", "desired_learning": "Existing workarounds"},
            {"section_index": 1, "section_title": "Workarounds", "question_index": 3, "main_question": "How well is that working for you? What's still missing?", "interview_notes": "", "desired_learning": "Gaps in current solution"},
            {"section_index": 2, "section_title": "Ideal solution", "question_index": 4, "main_question": "If you could wave a magic wand and fix this, what would happen?", "interview_notes": "Open-ended. Let them dream.", "desired_learning": "Their mental model of ideal"},
            {"section_index": 2, "section_title": "Ideal solution", "question_index": 5, "main_question": "If we built [proposed feature], how would you use it? Would it actually solve the problem for you?", "interview_notes": "Only describe the feature briefly. Don't oversell.", "desired_learning": "Fit of the proposed solution"},
        ],
    },
    {
        "id": "onboarding-friction",
        "name": "Onboarding Friction Study",
        "category": "saas",
        "icon": "🚀",
        "description": "Find out where new users get confused, blocked, or drop off during their first sessions with your product.",
        "best_for": "Product teams with low activation rates",
        "duration_minutes": 20,
        "research_objective": "Identify the specific friction points during the first-time user experience that prevent users from reaching their first 'aha moment'.",
        "target_audience": "Users who signed up in the last 14 days, including both activated and non-activated accounts.",
        "learning_goals": [
            "What were they hoping to accomplish in their first session?",
            "Where did they get stuck, confused, or lost?",
            "What would have helped them succeed faster?",
        ],
        "screening_questions": [
            {
                "question": "When did you first sign up for our product?",
                "options": ["Within the last 7 days", "1–2 weeks ago", "2–4 weeks ago", "More than a month ago"],
                "disqualifying_options": ["More than a month ago"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "First impressions", "question_index": 0, "main_question": "Tell me what brought you to sign up. What were you hoping to do with it?", "interview_notes": "Understand the job-to-be-done.", "desired_learning": "Initial expectations and goals"},
            {"section_index": 0, "section_title": "First impressions", "question_index": 1, "main_question": "Walk me through your first session. What did you try to do first?", "interview_notes": "Chronological — first click, first action.", "desired_learning": "Initial path through product"},
            {"section_index": 1, "section_title": "Friction", "question_index": 2, "main_question": "Was there a moment you felt stuck or confused? What was happening?", "interview_notes": "Probe for specifics. 'What did the screen look like?'", "desired_learning": "Friction points"},
            {"section_index": 1, "section_title": "Friction", "question_index": 3, "main_question": "What did you do when you got stuck? Did you figure it out, ask for help, or give up?", "interview_notes": "", "desired_learning": "Self-serve vs. dropout"},
            {"section_index": 2, "section_title": "First value", "question_index": 4, "main_question": "Was there a moment the product clicked for you — where you saw 'oh, this is useful'?", "interview_notes": "", "desired_learning": "Aha moment (or absence of one)"},
            {"section_index": 2, "section_title": "First value", "question_index": 5, "main_question": "What would have made your first session smoother or faster?", "interview_notes": "", "desired_learning": "Concrete improvement ideas"},
        ],
    },
    {
        "id": "pricing-research",
        "name": "Pricing & Willingness to Pay",
        "category": "saas",
        "icon": "💰",
        "description": "Test how customers perceive your pricing, what they'd be willing to pay, and which value drivers justify which tiers.",
        "best_for": "Teams repricing or launching a new tier",
        "duration_minutes": 20,
        "research_objective": "Understand how target customers perceive our pricing and value, and identify the price point and packaging that would maximize conversion without leaving money on the table.",
        "target_audience": "Prospects or current customers in your target segment who have an active need for this category of product.",
        "learning_goals": [
            "Which features or outcomes do they value the most?",
            "What's their mental reference point for pricing in this category?",
            "Where's their price resistance and where do they see a bargain?",
        ],
        "screening_questions": [
            {
                "question": "Are you currently evaluating or using a tool in this category?",
                "options": ["Yes, evaluating", "Yes, currently paying", "No, but interested", "No, not interested"],
                "disqualifying_options": ["No, not interested"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "Context", "question_index": 0, "main_question": "What does your team use today to solve [problem space], and what does that cost you?", "interview_notes": "Understand reference pricing.", "desired_learning": "Existing spend and tools"},
            {"section_index": 0, "section_title": "Context", "question_index": 1, "main_question": "What's the value you get from that, in your own words?", "interview_notes": "", "desired_learning": "Value framing"},
            {"section_index": 1, "section_title": "Value drivers", "question_index": 2, "main_question": "If you imagine an ideal tool for this, what features or outcomes would matter most?", "interview_notes": "Rank-order if possible.", "desired_learning": "Value hierarchy"},
            {"section_index": 1, "section_title": "Value drivers", "question_index": 3, "main_question": "Which of those would you be willing to pay a premium for? Which feel like table stakes?", "interview_notes": "", "desired_learning": "Price-sensitive vs. premium features"},
            {"section_index": 2, "section_title": "Pricing reaction", "question_index": 4, "main_question": "If I told you a tool like this cost €X per month per user, what would your reaction be?", "interview_notes": "Use Van Westendorp framing: too cheap / bargain / expensive / too expensive.", "desired_learning": "Price perception"},
            {"section_index": 2, "section_title": "Pricing reaction", "question_index": 5, "main_question": "How would you decide between a cheaper basic tier and a more expensive pro tier? What's in the pro tier that would move you?", "interview_notes": "", "desired_learning": "Tier-move triggers"},
        ],
    },
    {
        "id": "product-market-fit",
        "name": "Product-Market Fit Discovery",
        "category": "startup",
        "icon": "🎯",
        "description": "Early-stage validation: understand who your best users are, what job they're hiring you for, and whether the pain is real.",
        "best_for": "Founders in pre-launch or early-growth stage",
        "duration_minutes": 25,
        "research_objective": "Validate the target user segment, the job-to-be-done, and the strength of the pain point to determine if there is genuine product-market fit and which segment leads the way.",
        "target_audience": "People who fit the hypothetical target persona and who actively experience the problem we believe we're solving.",
        "learning_goals": [
            "Is the pain point real and frequent enough to pay for?",
            "Who is the best-fit customer and why?",
            "What would they do if our product didn't exist?",
        ],
        "screening_questions": [
            {
                "question": "In the last month, have you personally experienced [problem space]?",
                "options": ["Yes, frequently", "Yes, occasionally", "Rarely", "Never"],
                "disqualifying_options": ["Never"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "Context", "question_index": 0, "main_question": "Tell me about your role and what a typical week looks like for you.", "interview_notes": "Understand their world.", "desired_learning": "Role and context"},
            {"section_index": 0, "section_title": "Context", "question_index": 1, "main_question": "What are the biggest challenges you're dealing with right now in [relevant area]?", "interview_notes": "", "desired_learning": "Top-of-mind pain points"},
            {"section_index": 1, "section_title": "The problem", "question_index": 2, "main_question": "Walk me through the last time you dealt with [problem space]. What did that look like?", "interview_notes": "Concrete recent example.", "desired_learning": "Real workflow"},
            {"section_index": 1, "section_title": "The problem", "question_index": 3, "main_question": "On a scale of painful to 'no big deal', how frustrating is that for you?", "interview_notes": "Probe for why.", "desired_learning": "Pain intensity"},
            {"section_index": 2, "section_title": "Alternatives", "question_index": 4, "main_question": "How do you handle it today? What tools, processes, or hacks do you use?", "interview_notes": "", "desired_learning": "Current solutions"},
            {"section_index": 2, "section_title": "Alternatives", "question_index": 5, "main_question": "Have you ever tried to pay someone or buy a tool to make this go away?", "interview_notes": "", "desired_learning": "Willingness to pay history"},
            {"section_index": 3, "section_title": "Solution fit", "question_index": 6, "main_question": "If you could wave a magic wand, how would this problem disappear?", "interview_notes": "Let them describe their ideal.", "desired_learning": "Ideal solution shape"},
        ],
    },
    {
        "id": "customer-discovery",
        "name": "Customer Discovery Interviews",
        "category": "startup",
        "icon": "🔍",
        "description": "Open-ended interviews to learn about your target customer's world, their daily pains, and where your product could fit in.",
        "best_for": "Founders and PMs exploring a new opportunity",
        "duration_minutes": 25,
        "research_objective": "Build a deep understanding of the target customer's context, pain points, current workflows, and unmet needs to inform product direction and positioning.",
        "target_audience": "People who match the hypothetical target persona and are willing to share their workflows and challenges openly.",
        "learning_goals": [
            "What does a typical day look like for this persona?",
            "What are their biggest unmet needs in our problem space?",
            "What language do they use to describe their work and pains?",
        ],
        "screening_questions": [],
        "questions": [
            {"section_index": 0, "section_title": "Their world", "question_index": 0, "main_question": "Tell me about your role and your team. Who do you work with day-to-day?", "interview_notes": "Warm-up and context-setting.", "desired_learning": "Role and team structure"},
            {"section_index": 0, "section_title": "Their world", "question_index": 1, "main_question": "What does a typical week look like for you?", "interview_notes": "", "desired_learning": "Workflow texture"},
            {"section_index": 1, "section_title": "Pain points", "question_index": 2, "main_question": "What are the hardest or most frustrating parts of your job right now?", "interview_notes": "", "desired_learning": "Top pains, in their words"},
            {"section_index": 1, "section_title": "Pain points", "question_index": 3, "main_question": "Tell me about the last time one of those really slowed you down. What happened?", "interview_notes": "Concrete story.", "desired_learning": "Real examples"},
            {"section_index": 2, "section_title": "Tools & workarounds", "question_index": 4, "main_question": "What tools or processes do you use to get your work done? Which ones do you love, and which ones frustrate you?", "interview_notes": "", "desired_learning": "Current stack"},
            {"section_index": 2, "section_title": "Tools & workarounds", "question_index": 5, "main_question": "If you could change one thing about how your team works, what would it be?", "interview_notes": "", "desired_learning": "Opportunity areas"},
        ],
    },
    {
        "id": "brand-perception",
        "name": "Brand & Messaging Perception",
        "category": "marketing",
        "icon": "🎨",
        "description": "Test how your brand, tagline, and key messages land with your target audience.",
        "best_for": "Marketers refreshing positioning or a landing page",
        "duration_minutes": 15,
        "research_objective": "Understand how our target audience perceives our brand and core messaging, and identify which words and framings resonate or fall flat.",
        "target_audience": "People who match our target customer persona but have no prior strong opinion of the brand.",
        "learning_goals": [
            "What does our brand evoke in their minds before and after exposure?",
            "Which messages feel clear, which feel confusing, which feel exciting?",
            "What words would they use to describe what we do?",
        ],
        "screening_questions": [
            {
                "question": "Have you heard of our brand before?",
                "options": ["Never", "Name sounds familiar", "Yes, I know what they do", "Yes, I'm a customer"],
                "disqualifying_options": ["Yes, I'm a customer"],
            },
        ],
        "questions": [
            {"section_index": 0, "section_title": "First reaction", "question_index": 0, "main_question": "When I say the name [brand], what's the first thing that comes to mind?", "interview_notes": "Top-of-mind association.", "desired_learning": "Unprompted associations"},
            {"section_index": 0, "section_title": "First reaction", "question_index": 1, "main_question": "What do you think this company does, based just on the name or what you've seen?", "interview_notes": "", "desired_learning": "Perceived category"},
            {"section_index": 1, "section_title": "Messaging", "question_index": 2, "main_question": "I'll read you a tagline. Tell me what it makes you feel or think: '[TAGLINE]'", "interview_notes": "Pause after reading. Let them react.", "desired_learning": "Tagline reception"},
            {"section_index": 1, "section_title": "Messaging", "question_index": 3, "main_question": "Does that tagline make it clearer what the product is, or more confusing?", "interview_notes": "", "desired_learning": "Clarity"},
            {"section_index": 2, "section_title": "Competitive framing", "question_index": 4, "main_question": "If you had to describe what we do to a friend, how would you do it?", "interview_notes": "", "desired_learning": "Natural language framing"},
        ],
    },
]


def get_templates() -> List[ProjectTemplate]:
    """Return all available templates."""
    return TEMPLATES


def get_template_by_id(template_id: str) -> ProjectTemplate | None:
    """Look up a template by its id. Returns None if not found."""
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    return None
