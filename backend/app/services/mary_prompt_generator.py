"""
services/mary_prompt_generator.py
----------------------------------
Generates AI-varied prompts for Mary testing.
Produces a mix of:
  - Business-idea specific: user has a tool in mind and asks Mary for help
  - General help-seeking: user is confused about the screen and asks Mary
Called by the Mary batch runner.
"""

import json
import os
import random
import anthropic

# ---------------------------------------------------------------------------
# Seed prompts — used as fallback if AI generation fails
# Each entry: (screen, prompt, prompt_type)
# prompt_type: "specific" | "general"
# ---------------------------------------------------------------------------

SEED_PROMPTS = {
    "welcome": [
        ("welcome", "Hi Mary, what exactly is Physis and how does it work?", "general"),
        ("welcome", "I have an idea for a fitness tracking app — is this the right place to build it?", "specific"),
        ("welcome", "Can Physis build something for my small restaurant business?", "specific"),
        ("welcome", "I'm not a developer. Can I really build an AI tool here?", "general"),
        ("welcome", "What kinds of tools can Physis actually make?", "general"),
        ("welcome", "I want to build something that helps coaches track athlete progress — is that possible here?", "specific"),
        ("welcome", "How long does it take to build a tool on Physis?", "general"),
        ("welcome", "I run a tutoring business — can Physis help me build something for my students?", "specific"),
    ],
    "questionnaire": [
        ("questionnaire", "I'm building a meal planning tool — what should I put for the output format?", "specific"),
        ("questionnaire", "I'm not sure what 'interaction style' means — can you explain?", "general"),
        ("questionnaire", "My tool is for real estate agents to generate property descriptions. What tone should I pick?", "specific"),
        ("questionnaire", "How detailed should I be when describing what my tool creates?", "general"),
        ("questionnaire", "I want to build a budget tracker for college students — any tips on describing the target user?", "specific"),
        ("questionnaire", "What's the difference between simple, standard, and advanced complexity?", "general"),
        ("questionnaire", "I'm building something for HR managers to write job descriptions — what special rules should I add?", "specific"),
        ("questionnaire", "I don't know what to put for success measures — what does that mean?", "general"),
    ],
    "naming": [
        ("naming", "I'm building a recipe generator for vegans — what makes a good name for that?", "specific"),
        ("naming", "None of these names feel right for my legal document tool. What should I look for?", "specific"),
        ("naming", "Does the subdomain name matter for SEO or sharing?", "general"),
        ("naming", "My tool helps personal trainers write workout plans — any naming tips?", "specific"),
        ("naming", "Should I pick a fun name or a professional one for my business invoicing tool?", "specific"),
        ("naming", "What if I want to use my own brand name instead?", "general"),
        ("naming", "I'm building a tool for teachers to generate quiz questions — how do I pick between these three names?", "specific"),
        ("naming", "Can I change the name later after it's built?", "general"),
    ],
    "building": [
        ("building", "What exactly is Physis doing right now while my meal planning tool is being built?", "specific"),
        ("building", "How do the 17 quality tests work?", "general"),
        ("building", "It's been a minute — is my tool still being built or did something go wrong?", "general"),
        ("building", "What happens if a test fails during the build?", "general"),
        ("building", "My invoice generator is being built — will it have a professional look?", "specific"),
        ("building", "What does 'deploying to the web' mean exactly?", "general"),
        ("building", "Will my fitness tracker tool work on mobile phones too?", "specific"),
        ("building", "What should I do while I wait for my tool to finish building?", "general"),
    ],
    "complete": [
        ("complete", "My recipe tool is live! How do I share it with my cooking community?", "specific"),
        ("complete", "Can I customize the look of my tool after it's been built?", "general"),
        ("complete", "My budget tracker is live — how do I make sure my data stays private?", "specific"),
        ("complete", "What happens if I want to add more features to my tool later?", "general"),
        ("complete", "My workout planner is live — how do I get my gym clients to start using it?", "specific"),
        ("complete", "Can I build another tool that connects to this one?", "general"),
        ("complete", "My tool for writing job descriptions is live — can I embed it on my website?", "specific"),
        ("complete", "How do I know if people are actually using my tool?", "general"),
    ],
}

BUSINESS_IDEAS = [
    ("fitness coach", "workout plan generator for personal trainers"),
    ("restaurant owner", "weekly menu planner for small restaurants"),
    ("HR manager", "job description writer for hiring teams"),
    ("real estate agent", "property listing description generator"),
    ("teacher", "quiz and test question generator for classrooms"),
    ("nutritionist", "meal plan generator for clients with dietary restrictions"),
    ("accountant", "invoice generator for freelancers"),
    ("life coach", "goal setting and progress tracker for clients"),
    ("event planner", "vendor checklist and timeline generator"),
    ("dog trainer", "training plan generator for pet owners"),
    ("therapist", "session notes summarizer for mental health practices"),
    ("marketing manager", "social media caption generator for brands"),
    ("lawyer", "legal document template generator for small firms"),
    ("tutor", "personalized study plan generator for students"),
    ("interior designer", "room mood board and shopping list generator"),
]

GENERAL_HELP_TOPICS = {
    "welcome": [
        "what Physis is and what kinds of tools it can build",
        "whether non-technical people can use Physis",
        "how long it takes to build a tool",
        "what the difference is between simple and advanced tools",
    ],
    "questionnaire": [
        "what interaction style means",
        "how detailed answers should be",
        "what the complexity options mean",
        "what success measures are",
        "how to describe the target user",
    ],
    "naming": [
        "what makes a good tool name",
        "whether the subdomain matters",
        "how to choose between the suggested names",
        "whether they can use their own brand name",
    ],
    "building": [
        "what is happening during the build",
        "what the 17 quality tests check",
        "what to do if the build takes too long",
        "what deploying to the web means",
    ],
    "complete": [
        "how to share the tool with others",
        "whether they can customize the tool after building",
        "how to embed the tool on their website",
        "what to do if they want to add features later",
    ],
}

SCREENS = ["welcome", "questionnaire", "naming", "building", "complete"]

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def get_seed_prompts(count: int) -> list[dict]:
    """Return a random sample of seed prompts spread across all screens."""
    all_seeds = []
    for screen, prompts in SEED_PROMPTS.items():
        for _screen, prompt_text, prompt_type in prompts:
            all_seeds.append({
                "screen": screen,
                "prompt": prompt_text,
                "prompt_type": prompt_type,
                "source": "seed",
            })
    random.shuffle(all_seeds)
    return all_seeds[:count]


def generate_ai_prompts(count: int) -> list[dict]:
    """
    Use Claude to generate realistic, varied prompts for Mary testing.
    Mix of specific (user has a business idea) and general (user needs help).
    Spread across all 5 screens.
    """
    per_screen = max(1, count // len(SCREENS))
    remainder = count - (per_screen * len(SCREENS))

    # Pick random business ideas and help topics for variety
    selected_ideas = random.sample(BUSINESS_IDEAS, min(len(BUSINESS_IDEAS), max(3, count // 3)))
    ideas_text = "\n".join(
        f"- A {role} building a {tool}"
        for role, tool in selected_ideas
    )

    prompt = f"""You are generating test prompts for Mary, the AI guide inside Physis — an AI factory that builds web tools from plain English descriptions.

Mary appears on 5 screens: welcome, questionnaire, naming, building, complete.

Generate exactly {count} realistic prompts that users might ask Mary. Each prompt must be on one of the 5 screens.

Use these real business ideas for "specific" prompts:
{ideas_text}

Rules:
- "specific" prompts: user has a real business tool in mind and asks Mary for help related to THAT tool on THAT screen
- "general" prompts: user is confused about the screen itself and asks for general guidance
- Mix roughly 50% specific and 50% general
- Sound like a real non-technical person — natural, sometimes unsure
- Spread prompts across all 5 screens (roughly {per_screen} per screen)
- Each prompt should be a genuine question, not a statement

Return ONLY a JSON array, no markdown, no explanation:
[
  {{"screen": "welcome|questionnaire|naming|building|complete", "prompt": "...", "prompt_type": "specific|general"}},
  ...
]"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    prompts = json.loads(raw)
    return [
        {
            "screen": p["screen"],
            "prompt": p["prompt"],
            "prompt_type": p.get("prompt_type", "general"),
            "source": "ai_generated",
        }
        for p in prompts
        if p.get("screen") in SCREENS and p.get("prompt")
    ]


def generate_mary_prompts(count: int = 10, use_ai: bool = True) -> list[dict]:
    """
    Generate Mary test prompts — mix of seed + AI-generated.
    When use_ai=True: half seed, half AI.
    When use_ai=False: seed only.
    """
    if count <= 0:
        return []

    if not use_ai:
        return get_seed_prompts(count)

    seed_count = max(1, count // 2)
    ai_count = count - seed_count

    seeds = get_seed_prompts(seed_count)

    try:
        ai_prompts = generate_ai_prompts(ai_count)
        return seeds + ai_prompts
    except Exception as e:
        print(f"AI prompt generation failed, falling back to seed: {e}")
        return get_seed_prompts(count)
