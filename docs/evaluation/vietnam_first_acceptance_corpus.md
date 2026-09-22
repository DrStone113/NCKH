# Vietnam-first acceptance corpus

Frozen corpus: `offline-acceptance-vn-4954` (4954 chunks), hash `f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a`.

## Source precedence

1. Vietnam Ministry/NIN normative guidance
2. Global public-health guidance
3. Foreign-government guidance
4. Other verified reference

## Chatbot utility gate

{
  "records_by_chatbot_intent": {
    "BODY_METRIC_SUPPORT": 1,
    "DIETARY_CONSTRAINT": 1,
    "DIETARY_RECOMMENDATION": 4033,
    "EXERCISE_RECOMMENDATION": 887,
    "FOOD_NUTRITION_LOOKUP": 3927,
    "HEALTH_NUTRITION_CONTEXT": 33,
    "MICRONUTRIENT_SUPPORT": 37,
    "PERSONAL_HEALTH_PLAN_SUPPORT": 171,
    "PHYSICAL_ACTIVITY_GUIDANCE": 887,
    "SAFETY_ESCALATION": 3
  },
  "excluded_low_chatbot_utility": 10,
  "utility_exclusions": "apps/backend/data/research_acceptance_vn/manifests/utility_exclusions.jsonl"
}

Vietnam-source records are 656 (13.24%); Vietnam-relevant records are 646 (13.04%). Copyright/reuse for Vietnamese FCT and NIN source prose remains limited; only project-authored factual normalizations were stored, so redistribution clearance is still required.
