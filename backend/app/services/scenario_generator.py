import os
import json
import random
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Complexity levels Physis's BuildRequest accepts. Each drawn scenario gets a
# random pick at draw time so simulator runs don't all look the same.
# ─────────────────────────────────────────────────────────────────────────────
COMPLEXITY_OPTIONS = ["simple", "medium", "advanced"]

# The 5 Physis template categories. Every scenario below maps to exactly one.
CATEGORY_NAMES = ["generators", "analyzers", "trackers", "assistants", "transformers"]


# ─────────────────────────────────────────────────────────────────────────────
# Scenario pool — 260 total, 52 per category. Every entry is a plain-English
# description a real non-technical user would type into the Physis
# questionnaire. Industries span healthcare, finance, legal, education,
# retail, hospitality, technology, nonprofit, real estate, fitness, food,
# entertainment, travel, and sports. User types span solo founders, small
# business owners, freelancers, corporate employees, students, parents,
# coaches, creators, and professionals.
# ─────────────────────────────────────────────────────────────────────────────

GENERATOR_SCENARIOS = [
    "I need a tool that writes business proposals for my consulting work",
    "Build me a social media caption writer for my bakery's Instagram posts",
    "I want a job description generator for my startup — I hire often and writing them takes forever",
    "Create a cold email writer that sounds like me, not a bot, for sales outreach",
    "I need product descriptions for my Shopify store — give me something that converts",
    "Build a press release writer for small company announcements",
    "I write grant proposals for a nonprofit and need help speeding that up",
    "Make me a podcast script writer — I do a weekly interview show",
    "I'm giving a best man speech and have writer's block — help me draft something",
    "Generate cover letters for job applications based on the job posting and my resume",
    "I'm a manager and need to write performance reviews — give me a template generator",
    "Create terms of service for my SaaS website",
    "I'm trying to use up what's in my fridge — generate recipes from whatever ingredients I have",
    "Build me a weekly workout plan generator for busy parents who have 30 minutes a day",
    "I teach middle school — make a lesson plan generator that aligns to standards",
    "I write a lifestyle blog and need help drafting full posts from a topic",
    "Generate Google Ads copy that actually gets clicks for local service businesses",
    "Write me a professional LinkedIn bio — I'm changing careers",
    "I'm pitching investors and need a pitch deck outline generator for a seed round",
    "I run a small business and need a weekly newsletter writer",
    "I'm a realtor and need property listing descriptions that don't sound generic",
    "Generate Instagram Reels scripts for my fitness coaching brand",
    "Make me a YouTube title and description generator — I'm tired of guessing",
    "I send email marketing campaigns and need subject lines and body copy generated",
    "I'm writing wedding vows and I'm stuck — help me",
    "Birthday message generator for business clients — keep it warm but professional",
    "I do home inspections and need a report generator from my notes",
    "I'm a parent of two picky eaters with a nut allergy — give me a meal plan generator",
    "Build a weekend travel itinerary generator — I give a city and days, you give me the plan",
    "We're having a baby and need a name generator with meanings",
    "I run onboarding at my company — generate a welcome email sequence for new hires",
    "I teach yoga and need a class flow generator I can customize",
    "Generate wedding toasts for people who have no idea what to say",
    "I'm helping my kid with college essays — outline generator, please",
    "I'm a personal trainer and need customized workout programs for clients",
    "Write HR policies for my 10-person startup — we have nothing in writing",
    "Customer win-back email generator — I have lapsed subscribers I want to bring back",
    "Build me a content calendar generator for Instagram, LinkedIn, and TikTok",
    "Recipe ingredient substitution generator — I'm out of buttermilk, what now",
    "Legal disclaimers for my coaching website",
    "I run a small business and need an employee handbook — generate the first draft",
    "Product launch announcement generator for my e-commerce store",
    "Fundraising appeal letter generator — I run a small animal rescue",
    "Bedtime stories for my toddler — generate short ones with a moral",
    "I'm a pastor and need sermon outline ideas based on a verse",
    "Sales pitch script generator — I sell to small businesses",
    "Thank you note generator for closing real estate deals",
    "I run corporate training workshops — generate the agenda and materials",
    "Real estate buyer welcome email sequence — from offer to closing",
    "Holiday greeting messages for my customer list — keep it personal",
    "I coach kids baseball — generate a practice plan for tonight",
    "Podcast show notes generator from my episode transcript",
]

ANALYZER_SCENARIOS = [
    "I want to paste in a bunch of customer reviews and see the overall sentiment",
    "Analyze my competitor's landing page and tell me what they do better than me",
    "Score resumes I'm hiring for against a job description",
    "Track my stock portfolio and analyze which positions are dragging me down",
    "I run surveys for my consulting clients — analyze the responses into themes",
    "Project risk assessment — I list the project details and you flag what could go wrong",
    "SEO content analyzer — does my blog post have a shot at ranking?",
    "Code reviewer for the Python scripts I write — spot bugs and style issues",
    "Legal contract clause analyzer for freelance agreements — flag the red flags",
    "Medical symptom checker for non-emergency stuff my kids get",
    "Home valuation tool for sellers — what should I list my house for?",
    "Instagram engagement analyzer — which of my posts actually perform?",
    "Customer churn predictor for my SaaS — who's about to cancel?",
    "Analyze my sales pipeline and tell me which deals are stuck",
    "Employee performance review analyzer — convert raw feedback into themes",
    "Find bottlenecks in our small business supply chain",
    "Market trend analyzer for crypto investors — am I early or late?",
    "Real estate investment property analyzer — is this duplex worth it?",
    "Brand sentiment tracker across Twitter, Instagram, and Reddit mentions",
    "Email open rate analyzer — why are my newsletters tanking?",
    "Website accessibility audit for a nonprofit that needs WCAG compliance",
    "Compare two job offers side by side — salary, benefits, all of it",
    "Grocery nutrition label analyzer — is this breakfast bar actually healthy?",
    "Recipe calorie and macro analyzer from the ingredients I paste in",
    "Fitness progress analyzer from my workout logs — am I actually getting stronger?",
    "Decode my kid's report card — what do these grades really mean?",
    "Freelancer tax deduction finder — I give you expenses, you tell me what's deductible",
    "Compare two insurance policies — which is better for a family of four?",
    "Privacy policy complexity analyzer — is mine readable or a legal wall of text?",
    "Analyze my Google Ads campaign performance and tell me what to kill",
    "Customer feedback theme identifier — group 200 survey responses automatically",
    "Podcast episode topic analyzer — which topics got the most listens?",
    "YouTube thumbnail effectiveness analyzer — why aren't people clicking?",
    "LinkedIn profile strength analyzer — would a recruiter actually click on me?",
    "Investment property ROI analyzer — cap rate, cash flow, the whole picture",
    "Classroom attendance pattern analyzer for a homeroom teacher",
    "Mental health journal mood analyzer — show me my pattern over time",
    "Sales call transcript analyzer — what objections keep coming up?",
    "Legal case precedent analyzer — pull relevant cases from my brief",
    "Grocery receipt analyzer — where is the money actually going?",
    "Book review analyzer for my small press — what do readers love or hate?",
    "Student essay feedback analyzer — spot grammar, structure, and clarity issues",
    "Website UX heuristics analyzer — where do users probably get stuck?",
    "Pull action items out of meeting transcripts — I record every Zoom",
    "Email tone analyzer — does this sound passive-aggressive?",
    "Brand logo similarity analyzer — are we stepping on someone's trademark?",
    "Press coverage impact analyzer — how much mileage did our launch get?",
    "Restaurant menu profitability analyzer — which dishes are losers?",
    "Business plan completeness analyzer — what's missing from my deck?",
    "Nonprofit donor engagement pattern analyzer — who's cooling off?",
    "Gym class attendance analyzer for a boutique fitness studio",
    "Patient satisfaction survey analyzer for a small dental practice",
]

TRACKER_SCENARIOS = [
    "Daily water intake tracker with gentle reminders through the day",
    "Weightlifting tracker — log exercises, sets, reps, and see strength over time",
    "Freelance project hours tracker so I actually bill what I work",
    "Personal reading tracker — books I've finished, pages per day, the works",
    "Small shop inventory tracker — stock levels, reorder alerts",
    "Employee PTO and time off balance tracker for a 20-person team",
    "Investment portfolio value tracker across my brokerage accounts",
    "Client onboarding milestone tracker for my agency — are we on schedule?",
    "Morning routine habit tracker — I have eight habits and need to check them off daily",
    "Sales pipeline deal tracker — stages, values, next actions",
    "Real estate lead follow-up tracker — when did I last touch each lead?",
    "Family grocery expense tracker by category",
    "Macros and calorie tracker — I need protein, carbs, fats, and fiber",
    "Sleep quality tracker — hours, interruptions, how I feel in the morning",
    "Medication tracker for my aging parent — reminders and refill alerts",
    "Monthly subscription tracker — show me everything I'm paying for",
    "90-day goal tracker broken into weekly checkpoints",
    "Daily time block tracker — did I actually use my planned blocks?",
    "Mood journal and tracker — I want to see trends, not just entries",
    "Book reading tracker — pages per day, what I'm currently reading",
    "Travel tracker — trips taken, miles flown, countries visited",
    "Houseplant watering schedule tracker — different plants need different cadences",
    "Pet vaccination and vet visit tracker for multiple dogs",
    "Home maintenance tracker — filters, batteries, seasonal tasks",
    "Car maintenance tracker — oil, tires, mileage-based reminders",
    "Kids chore completion tracker with weekly allowance totaling",
    "Savings account deposit tracker — am I on pace for my down payment?",
    "Crypto portfolio tracker — show me realized and unrealized gains",
    "Running mileage and pace tracker — I'm training for a half marathon",
    "Meditation streak tracker — daily sit time and consecutive days",
    "Gratitude journal tracker — three things each day, searchable over time",
    "College study session tracker by subject and hours",
    "Screen time tracker by app — I want to know where my day actually goes",
    "Electric bill and usage tracker — compare month over month",
    "Restaurant visits and rating tracker — my personal food diary",
    "Wine tasting tracker for the hobbyist — notes, ratings, regions",
    "Backyard garden harvest tracker — which veggies actually produced?",
    "DIY project progress tracker — phases, hours spent, what's left",
    "Language learning streak tracker for Duolingo-style progress",
    "Swim lap tracker for pool workouts — distance and stroke",
    "Recipe tried and rating tracker — family favorites only",
    "Friend and family birthday tracker with gift ideas per person",
    "Piano practice tracker — songs, exercises, minutes per day",
    "Side hustle income tracker — I do Etsy and Fiverr",
    "Consultant invoice payment status tracker — sent, paid, overdue",
    "Yoga class attendance tracker for a membership studio",
    "Charity donation tracker for year-end tax prep",
    "Client session attendance tracker for a therapist or coach",
    "Dog walk duration and distance tracker with a map per walk",
    "High school volunteer hours tracker for community service requirements",
    "Family church service attendance tracker",
    "Baby feeding and sleep tracker for brand-new parents",
]

ASSISTANT_SCENARIOS = [
    "Customer support agent for my online clothing store — handle returns and sizing",
    "Math tutor for middle schoolers — pre-algebra and algebra 1",
    "Career coach for people considering a big transition",
    "HR assistant that answers benefits questions the team asks me constantly",
    "Sales assistant that coaches reps through common objections",
    "Interview prep coach for software engineers — system design practice",
    "Recipe assistant — tell me what's in my fridge, I'll suggest dinners",
    "Travel planner for solo backpackers on a tight budget",
    "Personal finance advisor for first-time investors who don't trust themselves",
    "Legal guidance assistant for small business owners — point me to the right questions to ask a lawyer",
    "Medical triage assistant — is this symptom urgent or can it wait till Monday?",
    "Mental health peer support chatbot with crisis resource handoffs",
    "Career counseling assistant for graduating college seniors",
    "Spanish conversation practice partner — I'm studying for a trip",
    "Home cooking coach for beginners — step me through a recipe like a friend",
    "Home improvement advisor — I want to redo my bathroom on a budget",
    "Gardening help for first-time vegetable growers in zone 6",
    "Parenting tips assistant for toddler tantrums and picky eating",
    "Relationship advice assistant for couples going through a rough patch",
    "Business mentor for solopreneurs — a sounding board, not an employee",
    "Tax filing guidance assistant for freelancers — what am I missing?",
    "Insurance claim help assistant — walk me through a home insurance claim",
    "First-home-buyer guide — I don't know the first thing about this",
    "Personal shopping assistant for gift ideas by budget and recipient",
    "Event planning assistant for a 50-person birthday party",
    "Wedding planning assistant for brides who want to DIY most of it",
    "At-home fitness coach — I have dumbbells and a yoga mat, that's it",
    "Dietician assistant for meal planning with gluten-free constraints",
    "Baby feeding schedule assistant for new parents — when do I feed what?",
    "Elderly care coordinator for adult children managing parents from far away",
    "Dog behavior advisor for new owners of a rescue",
    "SaaS customer onboarding agent — automate first-time setup help",
    "Study buddy for medical school students — board prep questions",
    "Online dating profile coach — make my profile actually work",
    "Public speaking coach for a conference talk next month",
    "Resume writing assistant for career changers",
    "Cover letter coach for recent graduates with no experience",
    "Negotiation coach for salary conversations",
    "Speech therapy practice partner for adults who stutter",
    "Grief counselor companion — gentle support after loss",
    "Sleep coach for chronic insomnia",
    "Smoking cessation support companion with daily check-ins",
    "Marathon training assistant for first-time marathoners",
    "Guitar practice coach for intermediate players",
    "DIY electrical help for homeowners — when to DIY vs hire a pro",
    "Weekend handyman advisor for small repair jobs",
    "Personal stylist for a capsule wardrobe on a modest budget",
    "College application essay coach for high school seniors",
    "Graduate school application advisor — PhD track",
    "Wedding vendor coordinator — keep me on top of who's doing what",
    "Immigration paperwork guide for new arrivals to the US",
    "Adoption process guide for families starting the journey",
]

TRANSFORMER_SCENARIOS = [
    "Take any legal document I paste in and rewrite it in plain English",
    "Turn my Zoom meeting transcript into a clean list of action items",
    "Format my weekly sales report — I want consistent columns and headers",
    "Translate my Spanish customer emails to English",
    "Take technical documentation and rewrite it so a beginner can follow",
    "Turn a court ruling into a layperson summary I can explain to my family",
    "Clean up my podcast transcript and break it into paragraphs",
    "Summarize long email threads for new team members who got added late",
    "Generate inline documentation for my Python scripts",
    "Extract data from PDF invoices and spit out a spreadsheet",
    "Clean up messy spreadsheet columns — typos, inconsistent formats, the works",
    "Turn product photos into alt text descriptions for accessibility",
    "Format my quarterly financial report — consistent tables, clean headings",
    "Summarize a 40-page contract into a one-page executive summary",
    "Turn our HR policy manual into a plain English employee FAQ",
    "Summarize a research paper abstract into a Twitter thread",
    "Turn a news article into a three-bullet summary",
    "Convert my blog post into a LinkedIn carousel",
    "Adapt my video script into an Instagram Reel caption and hooks",
    "Turn my Keynote presentation into a PowerPoint file",
    "Turn long customer reviews into a concise pros and cons list",
    "Turn 200 survey responses into structured insights I can use",
    "Translate my medical report into something my grandmother can understand",
    "Convert my Zoom transcript into proper meeting minutes",
    "Turn a Slack thread into an email recap for leadership",
    "Convert a textbook chapter into study notes and flashcards",
    "Turn interview transcripts into highlight quotes for a YouTube video",
    "Convert my lecture notes into a flashcard deck for exam prep",
    "Translate legal disclaimers into plain English so readers actually read them",
    "Turn my product manual into a quick-start guide",
    "Convert an email thread into a decision log for my project files",
    "Generate chapter markers from a long YouTube video transcript",
    "Turn a recorded conference talk into a blog post draft",
    "Convert meeting chat logs into a follow-up action email",
    "Turn food labels into a calorie and macro breakdown",
    "Translate my insurance policy into plain English so I know what's covered",
    "Turn tax form instructions into a plain English how-to guide",
    "Scale a recipe up or down based on how many people are coming to dinner",
    "Convert a book chapter into a short podcast script",
    "Turn an academic paper into a social media thread",
    "Convert a spreadsheet of expenses into a categorized monthly report",
    "Turn a job description into a set of interview questions",
    "Convert a bank statement into a categorized spending summary",
    "Turn my resume into a LinkedIn headline and summary",
    "Convert product reviews into marketing testimonials we can use on the site",
    "Summarize a long customer email thread into a ticket priority note",
    "Turn a podcast episode into a newsletter edition",
    "Convert a Twitter thread into a full blog post draft",
    "Pull key takeaways from a webinar recording for a follow-up email",
    "Rewrite a YouTube video description to be SEO-friendly",
    "Rewrite corporate jargon into plain English",
    "Turn a legal filing into a press release draft",
]


# Flat pool of all 260 scenarios, each tagged with its Physis category so
# run_service.py's save_scenarios can store the category alongside the
# description. Complexity is NOT baked in here — it's assigned per draw so
# the same description can be fired at simple / medium / advanced builds.
SCENARIO_POOL: list[dict] = (
    [{"description": d, "category": "generators"}   for d in GENERATOR_SCENARIOS] +
    [{"description": d, "category": "analyzers"}    for d in ANALYZER_SCENARIOS] +
    [{"description": d, "category": "trackers"}     for d in TRACKER_SCENARIOS] +
    [{"description": d, "category": "assistants"}   for d in ASSISTANT_SCENARIOS] +
    [{"description": d, "category": "transformers"} for d in TRANSFORMER_SCENARIOS]
)

# Backwards-compatible alias — older callers reference SEED_SCENARIOS by name.
SEED_SCENARIOS = SCENARIO_POOL


client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _pick_complexity() -> str:
    """Random Physis complexity level, one of simple / medium / advanced."""
    return random.choice(COMPLEXITY_OPTIONS)


def get_seed_scenarios(count: int = 10) -> list[dict]:
    """
    Return up to `count` scenarios drawn without repetition from the 260-entry
    pool. Each draw gets a fresh random complexity so repeat calls exercise
    the full simple/medium/advanced spectrum. Stops at len(SCENARIO_POOL)
    if asked for more than the pool holds.
    """
    sample = random.sample(SCENARIO_POOL, min(count, len(SCENARIO_POOL)))
    return [
        {**s, "complexity": _pick_complexity(), "source": "seed"}
        for s in sample
    ]


def generate_ai_scenarios(count: int = 5, categories: list[str] = None) -> list[dict]:
    """Use Claude to generate new realistic human-like Physis descriptions."""
    if not categories:
        categories = CATEGORY_NAMES

    prompt = f"""You are generating test inputs for an AI web app builder called Physis.
Physis takes plain English descriptions from real users and builds complete web apps.

Generate {count} realistic, diverse test descriptions that sound like real people writing naturally.
Mix simple and complex requests. Map each to one of the 5 Physis template categories: {', '.join(categories)}.

Return ONLY a JSON array, no markdown, no explanation. Format:
[
  {{"description": "...", "category": "...", "complexity": "simple|medium|advanced"}},
  ...
]

Rules:
- Write like a real non-technical person would
- Vary length and detail
- Some people give vague requests, some give very specific ones
- Do NOT use technical jargon
- Categories must be one of: {', '.join(categories)}
- Complexity must be one of: simple, medium, advanced"""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    scenarios = json.loads(raw)
    return [{**s, "source": "ai_generated"} for s in scenarios]


def generate_scenarios(count: int = 10, use_ai: bool = True) -> list[dict]:
    """
    Generate scenarios using a mix of seed + AI variation.
    When use_ai=True: half seed, half AI-generated.
    When use_ai=False: full count from seed pool.
    """
    if count <= 0:
        return []

    if not use_ai:
        return get_seed_scenarios(count)

    seed_count = max(1, count // 2)
    ai_count = count - seed_count

    seeds = get_seed_scenarios(seed_count)

    try:
        ai_scenarios = generate_ai_scenarios(ai_count)
        return seeds + ai_scenarios
    except Exception as e:
        print(f"AI generation failed, falling back to seed only: {e}")
        extras = get_seed_scenarios(count)  # draw full count from the pool
        # deduplicate by description
        seen = {s["description"] for s in seeds}
        unique_extras = [s for s in extras if s["description"] not in seen]
        return seeds + unique_extras[:ai_count]
