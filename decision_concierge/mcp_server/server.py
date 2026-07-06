"""Real MCP server (Day 2): exposes deterministic finance tools over stdio so
any MCP-compatible agent — not just this one — can call them. Deterministic
math lives here rather than being left to the LLM, and the product catalog is
a small static mock (clearly labeled), standing in for a real price/review API.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("decision-concierge-tools")

_MOCK_CATALOG = {
    "macbook air m4": {"price": 1099, "rating": 4.7, "category": "laptop"},
    "macbook pro": {"price": 1999, "rating": 4.8, "category": "laptop"},
    "iphone 17": {"price": 999, "rating": 4.6, "category": "phone"},
    "asus zenbook": {"price": 899, "rating": 4.4, "category": "laptop"},
    "rog phone": {"price": 899, "rating": 4.5, "category": "phone"},
    "pixel 10": {"price": 799, "rating": 4.5, "category": "phone"},
}


@mcp.tool()
def affordability_calculator(monthly_income: float, price: float) -> dict:
    """Given monthly income and an item's price, return affordability verdict."""
    if monthly_income <= 0:
        return {"pct_of_income": None, "verdict": "unknown"}
    pct = round((price / monthly_income) * 100, 1)
    if pct <= 15:
        verdict = "comfortable"
    elif pct <= 35:
        verdict = "manageable"
    else:
        verdict = "stretch"
    return {"pct_of_income": pct, "verdict": verdict}


@mcp.tool()
def budget_allocator(monthly_income: float, fixed_expenses: float) -> dict:
    """50/30/20-style allocation of remaining income after fixed expenses."""
    remaining = max(monthly_income - fixed_expenses, 0)
    return {
        "fixed_expenses": fixed_expenses,
        "savings_target": round(remaining * 0.5, 2),
        "discretionary": round(remaining * 0.3, 2),
        "buffer": round(remaining * 0.2, 2),
        "remaining_after_fixed": round(remaining, 2),
    }


@mcp.tool()
def product_price_lookup(item: str) -> dict:
    """Mock price/rating catalog lookup — swap for a real price/review MCP server in production."""
    key = item.strip().lower()
    for name, data in _MOCK_CATALOG.items():
        if name in key or key in name:
            return {"match": name, "source": "mock_catalog", **data}
    return {
        "match": None,
        "source": "mock_catalog",
        "price": None,
        "rating": None,
        "note": "no catalog match — treat as unverified estimate",
    }


# Illustrative, deliberately tiny interaction/ingredient table standing in for a
# real drug-interaction API (e.g. RxNorm/DrugBank). NOT medical data — swap for a
# licensed source in production. Keys are lowercased common names; each maps to
# the set of things it conflicts with.
_MOCK_INTERACTIONS = {
    "warfarin": {"aspirin", "ibuprofen", "naproxen", "vitamin k"},
    "aspirin": {"warfarin", "ibuprofen"},
    "ibuprofen": {"warfarin", "aspirin", "lisinopril"},
    "lisinopril": {"ibuprofen", "potassium", "spironolactone"},
    "tramadol": {"sertraline", "fluoxetine", "ssri"},
    "sertraline": {"tramadol", "maoi"},
    "simvastatin": {"grapefruit", "clarithromycin"},
    "pseudoephedrine": {"maoi", "phenelzine"},
}


@mcp.tool()
def drug_interaction_lookup(item: str, current_meds: str, allergies: str) -> dict:
    """Check a candidate medication/supplement against the user's stated current
    meds and allergies. Deterministic lookup against a small illustrative table —
    an organizer aid, NOT medical advice. Returns any allergy hit and interaction
    conflicts so the caller can flag them; it does not diagnose or prescribe."""
    cand = item.strip().lower()

    def _tokens(s: str) -> list[str]:
        return [t.strip() for t in s.replace(";", ",").split(",") if t.strip()]

    allergy_hit = next(
        (a for a in _tokens(allergies.lower()) if a and (a in cand or cand in a)),
        None,
    )

    cand_conflicts = _MOCK_INTERACTIONS.get(cand, set())
    interactions = [
        med for med in _tokens(current_meds.lower())
        if med in cand_conflicts or cand in _MOCK_INTERACTIONS.get(med, set())
    ]

    return {
        "candidate": cand,
        "source": "mock_interaction_table",
        "allergy_hit": allergy_hit,
        "interactions": interactions,
        "note": "illustrative table — not medical advice; verify with a pharmacist",
    }


# Illustrative, deliberately tiny nutrition table standing in for a real
# nutrition API (e.g. USDA FoodData Central). NOT nutrition advice — swap for a
# licensed source in production. Values per typical serving; tags describe diet
# suitability; allergens are common ones present.
_MOCK_NUTRITION = {
    "smoothie": {"sugar_g": 52, "sodium_mg": 90, "calories": 300, "allergens": {"milk"}, "tags": {"vegetarian"}},
    "soda": {"sugar_g": 39, "sodium_mg": 45, "calories": 150, "allergens": set(), "tags": {"vegetarian", "vegan"}},
    "instant ramen": {"sugar_g": 4, "sodium_mg": 1800, "calories": 380, "allergens": {"wheat", "egg", "soy"}, "tags": {"vegetarian"}},
    "cheeseburger": {"sugar_g": 9, "sodium_mg": 1100, "calories": 550, "allergens": {"milk", "wheat"}, "tags": set()},
    "peanut butter sandwich": {"sugar_g": 8, "sodium_mg": 350, "calories": 400, "allergens": {"peanut", "wheat"}, "tags": {"vegetarian"}},
    "grilled chicken salad": {"sugar_g": 6, "sodium_mg": 400, "calories": 350, "allergens": set(), "tags": set()},
    "green salad": {"sugar_g": 3, "sodium_mg": 120, "calories": 150, "allergens": set(), "tags": {"vegetarian", "vegan"}},
    "oatmeal": {"sugar_g": 12, "sodium_mg": 150, "calories": 250, "allergens": {"wheat"}, "tags": {"vegetarian", "vegan"}},
}


@mcp.tool()
def nutrition_lookup(item: str) -> dict:
    """Look up a food/dish's approximate nutrition, allergens, and diet tags from
    a small illustrative table. A goal-alignment aid, NOT nutrition advice — it
    reports numbers so the caller can compare them to the user's OWN stated goal;
    it never calls a food 'healthy' or 'unhealthy' as fact."""
    key = item.strip().lower()
    for name, data in _MOCK_NUTRITION.items():
        if name in key or key in name:
            return {
                "match": name,
                "source": "mock_nutrition_table",
                "sugar_g": data["sugar_g"],
                "sodium_mg": data["sodium_mg"],
                "calories": data["calories"],
                "allergens": sorted(data["allergens"]),
                "tags": sorted(data["tags"]),
                "note": "illustrative table — not nutrition advice",
            }
    return {
        "match": None,
        "source": "mock_nutrition_table",
        "sugar_g": None,
        "sodium_mg": None,
        "calories": None,
        "allergens": [],
        "tags": [],
        "note": "no match — treat as unverified; can't check against your goal",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
