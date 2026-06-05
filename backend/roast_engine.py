"""Template-based roast engine for Roast My Startup.

Deterministic-yet-varied generation: seeds RNG on hash(startup_name + description + level)
so each user gets a unique roast that's reproducible.
"""
from __future__ import annotations
import hashlib
import random
from typing import Dict, List, Tuple


ROAST_LEVELS = {
    "friendly": {
        "label": "Friendly Feedback",
        "tone": "supportive",
    },
    "reality": {
        "label": "Founder Reality Check",
        "tone": "sharp",
    },
    "investor": {
        "label": "Investor Mode",
        "tone": "professional",
    },
    "vcv": {
        "label": "Venture Capital Violence",
        "tone": "witty",
    },
}

SCORE_CATEGORIES = [
    (0, 30, "Danger Zone"),
    (31, 50, "Needs Work"),
    (51, 70, "Promising"),
    (71, 85, "Strong Potential"),
    (86, 100, "Investor Bait"),
]

ARCHETYPES = [
    ("The Visionary", "Sees a future so vivid that the present feels like a beta version. Just make sure customers can see it too."),
    ("The Builder", "Shipping is your love language. Now we need someone to fall in love with what you're building."),
    ("The Dream Seller", "Pitch deck has the polish of a Pixar trailer. The product, less so."),
    ("The Product Addict", "Three new features a week, zero new customers. Touch grass — and a CRM."),
    ("The Market Whisperer", "You actually know your customer. Rare. Now go tell more of them you exist."),
    ("The Buzzword Collector", "AI-powered, blockchain-enabled, web3-native, agentic, vertical SaaS. Pick two and commit."),
    ("The Silent Operator", "Quietly building real revenue while no one's watching. Marketing might want a word."),
]


# ---------- helpers ----------

def _seed(startup_name: str, description: str, level: str) -> random.Random:
    h = hashlib.sha256(f"{startup_name}|{description}|{level}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def _score_category(score: int) -> str:
    for lo, hi, label in SCORE_CATEGORIES:
        if lo <= score <= hi:
            return label
    return "Promising"


# ---------- scoring ----------

def calculate_score(
    *,
    description: str,
    website: str | None,
    stage: str | None,
    monthly_revenue: str | None,
    industry: str,
    rng: random.Random,
) -> Tuple[int, Dict[str, int]]:
    """Return overall score 0-100 and DNA breakdown."""

    desc_len = len(description.strip())
    # Clarity from description length & punctuation
    clarity_base = min(85, 30 + desc_len // 8) if desc_len > 0 else 20
    clarity = max(15, min(95, clarity_base + rng.randint(-12, 12)))

    # Market potential biased by industry
    hot_industries = {"ai", "fintech", "saas", "health", "developer tools", "climate", "biotech"}
    cold_industries = {"crypto", "nft", "metaverse", "web3"}
    ind_lower = industry.lower()
    market_base = 60
    if any(h in ind_lower for h in hot_industries):
        market_base = 78
    elif any(c in ind_lower for c in cold_industries):
        market_base = 45
    market = max(20, min(95, market_base + rng.randint(-15, 15)))

    # Differentiation — penalize buzzword density
    buzzwords = ["ai", "ai-powered", "blockchain", "web3", "revolutionary", "disrupt", "uber for", "airbnb for", "platform", "ecosystem"]
    buzz_hits = sum(1 for b in buzzwords if b in description.lower())
    diff_base = 65 - buzz_hits * 8
    differentiation = max(15, min(90, diff_base + rng.randint(-15, 15)))

    # Business model from revenue & stage
    bm_base = 40
    if monthly_revenue and any(ch.isdigit() for ch in str(monthly_revenue)):
        # crude parse
        digits = "".join(ch for ch in str(monthly_revenue) if ch.isdigit())
        try:
            mrr = int(digits[:9]) if digits else 0
        except Exception:
            mrr = 0
        if mrr >= 50000:
            bm_base = 88
        elif mrr >= 10000:
            bm_base = 78
        elif mrr >= 1000:
            bm_base = 65
        elif mrr > 0:
            bm_base = 55
    if stage:
        s = stage.lower()
        if "growing" in s:
            bm_base += 10
        elif "launched" in s:
            bm_base += 4
        elif "idea" in s:
            bm_base -= 12
    business_model = max(15, min(95, bm_base + rng.randint(-10, 10)))

    # Positioning — website presence matters
    pos_base = 55 + (10 if website and website.strip() else -8)
    if desc_len < 60:
        pos_base -= 10
    positioning = max(15, min(95, pos_base + rng.randint(-12, 12)))

    # Founder Delusion — purposely high (humorous)
    delusion_base = 70 + rng.randint(0, 25)
    if stage and "idea" in (stage or "").lower():
        delusion_base = min(99, delusion_base + 8)
    founder_delusion = max(40, min(99, delusion_base))

    # Overall (weighted, excludes delusion)
    overall = round(
        clarity * 0.18
        + market * 0.22
        + differentiation * 0.20
        + business_model * 0.22
        + positioning * 0.18
    )
    overall = max(5, min(99, overall))

    dna = {
        "clarity": clarity,
        "market_potential": market,
        "differentiation": differentiation,
        "business_model": business_model,
        "positioning": positioning,
        "founder_delusion": founder_delusion,
    }
    return overall, dna


# ---------- roast templates ----------

ANALOGY_TEMPLATES = {
    "friendly": [
        "Your startup is like a great novel with a confusing cover — once people open it, they'll stay, but you need to get them to open it.",
        "{name} feels like a coffee shop on a side street: real quality, not enough signage.",
        "Think of {name} as a strong second draft. The bones are there; the polish is the next mile.",
    ],
    "reality": [
        "Your startup is a Swiss Army knife in a world that needs scissors.",
        "{name} is a great answer to a question your customers haven't typed into Google yet.",
        "Right now {name} reads like a LinkedIn bio: every word is true, none of them are interesting.",
    ],
    "investor": [
        "{name} is positioned somewhere between 'too early' and 'too crowded' — investors call that the squeeze.",
        "Your deck would survive a five-minute meeting. We need it to survive a five-second one.",
        "The TAM slide is doing all the lifting. The wedge slide is on a coffee break.",
    ],
    "vcv": [
        "Your value proposition is hiding so effectively that even your customers cannot find it.",
        "{name} currently has the confidence of a unicorn and the clarity of IKEA instructions translated three times.",
        "Your differentiation strategy appears to be hoping competitors never notice you exist.",
        "Reading {description_short} feels like watching someone explain a joke to themselves in real time.",
    ],
}

INVESTOR_OBS_TEMPLATES = {
    "friendly": [
        "There's a real business in here. The job is to make the first sentence do 80% of the work.",
        "I'd take a meeting. I'd also ask for one slide that explains the wedge.",
    ],
    "reality": [
        "If this landed in my inbox at 9pm, I'd star it. I wouldn't reply until you sharpened the wedge.",
        "I can see the market. I cannot yet see your unfair advantage inside it.",
    ],
    "investor": [
        "If this landed in my inbox, I'd ask for clearer positioning before scheduling a meeting.",
        "Strong team-shaped energy. The narrative needs one more cycle before it earns a term sheet.",
    ],
    "vcv": [
        "If this came across my desk, my associate would write 'pass — interesting human, vague company' and we'd both move on.",
        "I'd forward this to a partner, but only as a polite way of saying I'm not the lead.",
    ],
}

FOUNDER_JOKE_TEMPLATES = [
    "Your roadmap has more pivots than a basketball game.",
    "You spent four weekends on the logo and four minutes on the pricing page.",
    "Your CAC is unknown because you haven't acquired a customer yet — technically infinite, technically efficient.",
    "Your competitors slide is suspiciously empty. So is your customer list.",
    "Your demo video is in 4K. Your homepage copy is in 240p.",
    "You're A/B testing the hero before you've B-tested the business model.",
]

PRACTICAL_INSIGHT_TEMPLATES = [
    "Rewrite your one-liner so a tired commuter understands it. If it survives that, it survives investors.",
    "Pick one ICP for the next 60 days. Say no to everyone else, even the tempting ones.",
    "Replace adjectives with numbers. 'Fast' becomes '3x faster'. 'Easy' becomes 'setup in 4 minutes'.",
    "Run five sales calls this week with prospects you haven't met. The roadmap will rewrite itself.",
    "Charge sooner. Free pilots produce free feedback. Paying customers produce a business.",
]

WHAT_WORKS_POOL = [
    "A real problem worth solving — the pain is legible.",
    "Clear founder energy: the description reads like a person, not a committee.",
    "A defensible niche if you stay disciplined about scope.",
    "Industry tailwinds are on your side for the next 18 months.",
    "Pricing posture is closer to 'business' than to 'hobby project'.",
    "Distribution surface is bigger than the deck suggests.",
]

WHAT_NEEDS_WORK_POOL = [
    "Positioning is generic — three competitors could swap your tagline and nobody would notice.",
    "Messaging leans on features when it should sell outcomes.",
    "Differentiation reads as 'better' rather than 'different'.",
    "ICP is everyone, which is mathematically the same as no one.",
    "Pricing page is doing PR work, not commerce work.",
    "Onboarding is a tour when it should be a result in under 5 minutes.",
]

REALITY_CHECK_POOL = [
    "Your biggest challenge is not building the product. It's helping people understand why it matters.",
    "Nobody is waiting for {name}. You'll have to interrupt their day and make it worth it.",
    "Founders confuse motion for traction. Until someone pays, you're rehearsing.",
    "The market doesn't reward effort. It rewards clarity at the exact moment of need.",
]

HIGH_IMPACT_POOL = [
    "Pick one customer segment, one outcome, one price. Put it above the fold. Defend it for 90 days.",
    "Replace your homepage hero with a 12-word sentence and a 30-second product demo.",
    "Ship a public case study with one customer, real numbers, real screenshots. It will outperform your ads.",
    "Run a paid pilot priced 3x what feels comfortable. The friction will sharpen the product.",
]


def _pick(rng: random.Random, items: List, n: int = 1):
    if n == 1:
        return rng.choice(items)
    rng_items = items[:]
    rng.shuffle(rng_items)
    return rng_items[:n]


def generate_roast(
    *,
    startup_name: str,
    description: str,
    industry: str,
    website: str | None = None,
    stage: str | None = None,
    monthly_revenue: str | None = None,
    level: str = "reality",
) -> Dict:
    if level not in ROAST_LEVELS:
        level = "reality"

    rng = _seed(startup_name, description, level)
    score, dna = calculate_score(
        description=description,
        website=website,
        stage=stage,
        monthly_revenue=monthly_revenue,
        industry=industry,
        rng=rng,
    )

    name = startup_name.strip() or "Your startup"
    desc_short = (description.strip()[:80] + "…") if len(description.strip()) > 80 else description.strip()

    def fmt(template: str) -> str:
        return template.format(name=name, description_short=desc_short, industry=industry)

    analogy = fmt(_pick(rng, ANALOGY_TEMPLATES[level]))
    investor_obs = fmt(_pick(rng, INVESTOR_OBS_TEMPLATES[level]))
    founder_joke = fmt(_pick(rng, FOUNDER_JOKE_TEMPLATES))
    practical = fmt(_pick(rng, PRACTICAL_INSIGHT_TEMPLATES))

    what_works = [fmt(x) for x in _pick(rng, WHAT_WORKS_POOL, 3)]
    what_needs = [fmt(x) for x in _pick(rng, WHAT_NEEDS_WORK_POOL, 3)]
    reality_check = fmt(_pick(rng, REALITY_CHECK_POOL))
    high_impact = fmt(_pick(rng, HIGH_IMPACT_POOL))

    # Pick archetype biased on scores
    if dna["differentiation"] < 40:
        archetype_pool = ["The Dream Seller", "The Buzzword Collector", "The Product Addict"]
    elif dna["business_model"] >= 75:
        archetype_pool = ["The Silent Operator", "The Market Whisperer", "The Builder"]
    elif dna["founder_delusion"] >= 90:
        archetype_pool = ["The Visionary", "The Dream Seller", "The Buzzword Collector"]
    else:
        archetype_pool = [a[0] for a in ARCHETYPES]
    archetype_name = rng.choice(archetype_pool)
    archetype_desc = next(d for n, d in ARCHETYPES if n == archetype_name)

    # Best roast line for share card
    best_line = analogy

    return {
        "score": score,
        "score_category": _score_category(score),
        "level": level,
        "level_label": ROAST_LEVELS[level]["label"],
        "dna": dna,
        "archetype": {"name": archetype_name, "description": archetype_desc},
        "roast": {
            "analogy": analogy,
            "investor_observation": investor_obs,
            "founder_joke": founder_joke,
            "practical_insight": practical,
        },
        "what_works": what_works,
        "what_needs_work": what_needs,
        "investor_reaction": investor_obs,
        "reality_check": reality_check,
        "high_impact_improvement": high_impact,
        "best_line": best_line,
    }
