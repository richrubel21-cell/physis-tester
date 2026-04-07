import os
import json
import random
import anthropic
from dotenv import load_dotenv

load_dotenv()

SEED_SCENARIOS = [
    # Health & Fitness
    {"description": "I need a calorie tracker where I can log meals and see a weekly chart of my intake", "category": "health", "complexity": "medium"},
    {"description": "Build me a water intake tracker with reminders and a daily progress bar", "category": "health", "complexity": "simple"},
    {"description": "I want a workout log where I can track exercises, sets, reps, and weight over time", "category": "health", "complexity": "medium"},
    {"description": "Create a sleep tracker that lets me log hours and rate sleep quality with a monthly trend graph", "category": "health", "complexity": "simple"},
    {"description": "I need a BMI calculator with a chart showing healthy ranges and my history", "category": "health", "complexity": "simple"},

    # Finance
    {"description": "Build a budget tracker where I enter income and expenses by category and see a pie chart", "category": "finance", "complexity": "medium"},
    {"description": "I want a savings goal tracker where I set a target amount and log deposits toward it", "category": "finance", "complexity": "simple"},
    {"description": "Create a bill reminder app where I add recurring bills and get a monthly calendar view", "category": "finance", "complexity": "medium"},
    {"description": "I need a net worth calculator where I enter assets and debts and see my total over time", "category": "finance", "complexity": "simple"},
    {"description": "Build a subscription tracker so I can log all my monthly subscriptions and see the total cost", "category": "finance", "complexity": "simple"},

    # Productivity
    {"description": "I want a pomodoro timer with task input and a session history log", "category": "productivity", "complexity": "simple"},
    {"description": "Build a habit tracker where I add daily habits and check them off, with a streak counter", "category": "productivity", "complexity": "medium"},
    {"description": "Create a daily planner where I can schedule tasks by time block and mark them complete", "category": "productivity", "complexity": "medium"},
    {"description": "I need a note-taking app with tags, search, and the ability to pin important notes", "category": "productivity", "complexity": "medium"},
    {"description": "Build a goal setting tool where I define goals, break them into milestones, and track progress", "category": "productivity", "complexity": "complex"},

    # Business / Work
    {"description": "I need a client contact manager with name, email, phone, and last contact date", "category": "business", "complexity": "simple"},
    {"description": "Create an invoice generator where I fill in client info, line items, and download a PDF", "category": "business", "complexity": "complex"},
    {"description": "Build a project tracker with tasks, assignees, due dates, and a status board", "category": "business", "complexity": "complex"},
    {"description": "I want a meeting notes app where I log meetings, attendees, and action items", "category": "business", "complexity": "medium"},
    {"description": "Create a time tracking tool where I log hours per project and see weekly totals", "category": "business", "complexity": "medium"},

    # Fun / Creative
    {"description": "Build a movie watchlist where I add films, rate ones I've seen, and filter by genre", "category": "entertainment", "complexity": "medium"},
    {"description": "I need a recipe box where I save recipes with ingredients and steps and search by name", "category": "entertainment", "complexity": "medium"},
    {"description": "Create a book tracker where I log books I'm reading, finished, and want to read", "category": "entertainment", "complexity": "simple"},
    {"description": "Build a travel bucket list app where I add destinations with notes and mark visited ones", "category": "entertainment", "complexity": "simple"},
    {"description": "I want a random meal picker that shows me a random recipe from my saved list when I can't decide", "category": "entertainment", "complexity": "simple"},
]

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_seed_scenarios(count: int = 10) -> list[dict]:
    """Return a random sample from seed scenarios (copied, not mutated)."""
    sample = random.sample(SEED_SCENARIOS, min(count, len(SEED_SCENARIOS)))
    return [{**s, "source": "seed"} for s in sample]

def generate_ai_scenarios(count: int = 5, categories: list[str] = None) -> list[dict]:
    """Use Claude to generate new realistic human-like Physis descriptions."""
    if not categories:
        categories = ["health", "finance", "productivity", "business", "entertainment"]

    prompt = f"""You are generating test inputs for an AI web app builder called Physis.
Physis takes plain English descriptions from real users and builds complete web apps.

Generate {count} realistic, diverse test descriptions that sound like real people writing naturally.
Mix simple and complex requests. Use these categories: {', '.join(categories)}.

Return ONLY a JSON array, no markdown, no explanation. Format:
[
  {{"description": "...", "category": "...", "complexity": "simple|medium|complex"}},
  ...
]

Rules:
- Write like a real non-technical person would
- Vary length and detail
- Some people give vague requests, some give very specific ones
- Do NOT use technical jargon
- Categories must be one of: health, finance, productivity, business, entertainment"""

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
    When use_ai=False: full count from seed list.
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
        extras = get_seed_scenarios(count)  # just get full count from seeds
        # deduplicate by description
        seen = {s["description"] for s in seeds}
        unique_extras = [s for s in extras if s["description"] not in seen]
        return seeds + unique_extras[:ai_count]
