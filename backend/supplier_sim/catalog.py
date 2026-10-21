"""Synthetic packages for every supported destination. Prices are quoted for 3 travelers x 3 days.

Each destination deliberately mixes one stay whose access claims are well supported, one whose listing is
contradicted by guests, and one whose evidence is incomplete, so every verification path can be exercised.
Evidence rows are (claim, source, polarity, strength, detail) or, with a fixed reference, (..., reference).
"""

LIFT, STEP, BATH = "lift_serves_all_guest_floors", "step_free_entry", "accessible_bathroom"
STAY = ["Three-day accommodation", "Local transport", "Sample activities"]
STAY_WITH_TRANSFER = [*STAY, "Accessible airport transfer (wheelchair van)"]
STRICT = [{"days_before": 14, "refund_percent": 100}, {"days_before": 3, "refund_percent": 50}]
GENTLE = [{"days_before": 7, "refund_percent": 100}, {"days_before": 2, "refund_percent": 50}]
WEEK = [{"days_before": 7, "refund_percent": 100}]
EVERY_DIET = ["VEGETARIAN", "VEGAN", "GLUTEN_FREE", "HALAL", "DIABETIC", "LOW_SODIUM", "SOFT_FOOD"]


def stay(product_id, name, base_total, policy, evidence, *, lift, step, bath, walking, rating, diets=(), transfer=False):
    return {"product_id": product_id, "name": name, "base_total": base_total, "cancellation_policy": policy,
            "includes": STAY_WITH_TRANSFER if transfer else STAY,
            "attributes": {"lift_all_floors": lift, "step_free_entry": step, "accessible_bathroom": bath,
                           "walking_level": walking, "rating": rating, "dietary_options": list(diets),
                           "accessible_transfer": transfer},
            "evidence": evidence}


def verified(detail_lift, detail_step, detail_bath):
    return [(LIFT, "official_amenity", "SUPPORT", "STRONG", detail_lift),
            (STEP, "accessibility_audit", "SUPPORT", "STRONG", detail_step),
            (BATH, "accessibility_audit", "SUPPORT", "STRONG", detail_bath)]


CATALOG = {
    "Auckland": [
        stay("PACKAGE_A", "Harbour Lodge three-day stay", "820.00", STRICT, [
            # The listing claims a lift; guest reviews and a support ticket say otherwise.
            (LIFT, "official_amenity", "SUPPORT", "WEAK", "A lift is listed; floor coverage is unspecified.", "CAT-A-1"),
            (LIFT, "guest_review", "CONTRADICT", "STRONG", "A half-flight of stairs remains.", "REV-A-2"),
            (LIFT, "support_ticket", "CONTRADICT", "STRONG", "Guest reports stairs to accommodation.", "TKT-A-3"),
            (STEP, "official_amenity", "CONTRADICT", "STRONG", "The listing shows three steps at the entrance.", "CAT-A-4"),
            (BATH, "official_amenity", "CONTRADICT", "STRONG", "All rooms have a shower over the bath.", "CAT-A-5"),
        ], lift=True, step=False, bath=False, walking="MODERATE", rating=4.1, diets=["VEGETARIAN"]),
        stay("PACKAGE_C", "City Garden Hotel package", "880.00", WEEK, [
            (LIFT, "official_amenity", "UNKNOWN", "WEAK", "Guest-floor lift coverage is unlisted.", "CAT-C-1"),
            (STEP, "accessibility_audit", "SUPPORT", "STRONG", "Level entry from the drop-off zone.", "AUD-C-2"),
            (BATH, "official_amenity", "UNKNOWN", "WEAK", "Bathroom layout is not described.", "CAT-C-3"),
        ], lift=None, step=True, bath=None, walking="LOW", rating=4.4, diets=["VEGETARIAN", "GLUTEN_FREE"]),
        stay("PACKAGE_B", "Waterfront Accessible Suites", "920.00", GENTLE, [
            (LIFT, "official_amenity", "SUPPORT", "STRONG", "Lift serves all guest floors in the synthetic catalog.", "CAT-B-1"),
            (STEP, "accessibility_audit", "SUPPORT", "STRONG", "Automatic doors and level entry.", "AUD-B-2"),
            (BATH, "accessibility_audit", "SUPPORT", "STRONG", "Roll-in shower, grab rails and a shower seat.", "AUD-B-3"),
        ], lift=True, step=True, bath=True, walking="LOW", rating=4.6, diets=EVERY_DIET, transfer=True),
    ],
    "Queenstown": [
        stay("QTN_LAKEFRONT", "Lakefront Lodge on Lake Wakatipu", "960.00", GENTLE,
             verified("Two lifts serve every floor.", "Ramped, level entrance.", "Accessible suites with roll-in showers."),
             lift=True, step=True, bath=True, walking="LOW", rating=4.7, diets=EVERY_DIET, transfer=True),
        stay("QTN_ALPINE", "Alpine Chalet Retreat", "780.00", STRICT, [
            (LIFT, "official_amenity", "UNKNOWN", "WEAK", "Chalets are split-level; no lift is mentioned."),
            (STEP, "guest_review", "CONTRADICT", "STRONG", "A steep driveway and steps lead to every chalet."),
        ], lift=None, step=False, bath=None, walking="HIGH", rating=4.3, diets=["VEGETARIAN"]),
        stay("QTN_TOWN", "Town Centre Apartments", "890.00", WEEK, [
            (LIFT, "official_amenity", "SUPPORT", "STRONG", "Lift to all apartment floors."),
            (STEP, "official_amenity", "SUPPORT", "STRONG", "Street-level lobby."),
            (BATH, "official_amenity", "UNKNOWN", "WEAK", "Bathrooms are described as 'spacious' only."),
        ], lift=True, step=True, bath=None, walking="MODERATE", rating=4.2, diets=["VEGETARIAN", "GLUTEN_FREE"]),
    ],
    "Rotorua": [
        stay("ROT_SPA", "Lakeside Spa Resort", "940.00", GENTLE,
             verified("Lift and ramps reach every wing.", "Level entry and paths to the spa.", "Roll-in showers in six rooms."),
             lift=True, step=True, bath=True, walking="LOW", rating=4.5, diets=EVERY_DIET, transfer=True),
        stay("ROT_MOTEL", "Geyser View Motor Lodge", "690.00", WEEK, [
            (LIFT, "official_amenity", "SUPPORT", "WEAK", "Ground-floor units are available on request."),
            (STEP, "official_amenity", "SUPPORT", "STRONG", "Parking beside each ground-floor unit."),
            (BATH, "guest_review", "CONTRADICT", "STRONG", "Shower over the bath in every unit."),
        ], lift=True, step=True, bath=False, walking="LOW", rating=4.0, diets=[]),
        stay("ROT_HERITAGE", "Heritage Guesthouse", "760.00", STRICT, [
            (LIFT, "official_amenity", "CONTRADICT", "STRONG", "No lift; guest rooms are upstairs."),
            (STEP, "guest_review", "CONTRADICT", "STRONG", "Steps to the front veranda."),
        ], lift=False, step=False, bath=False, walking="MODERATE", rating=4.6, diets=["VEGETARIAN", "SOFT_FOOD"]),
    ],
    "Wellington": [
        stay("WLG_HARBOUR", "Harbourside Hotel", "970.00", GENTLE,
             verified("Lifts to all floors.", "Level entry from the waterfront.", "Accessible rooms with roll-in showers."),
             lift=True, step=True, bath=True, walking="LOW", rating=4.4, diets=EVERY_DIET, transfer=True),
        stay("WLG_BOUTIQUE", "Cuba Street Boutique Hotel", "870.00", WEEK, [
            (LIFT, "official_amenity", "SUPPORT", "WEAK", "A lift is listed."),
            (LIFT, "guest_review", "CONTRADICT", "STRONG", "The lift was out of service for weeks during my stay."),
            (STEP, "official_amenity", "SUPPORT", "STRONG", "Street-level entrance."),
        ], lift=True, step=True, bath=None, walking="MODERATE", rating=4.5, diets=["VEGETARIAN", "VEGAN"]),
        stay("WLG_HILLTOP", "Kelburn Hilltop B&B", "720.00", STRICT, [
            (STEP, "guest_review", "CONTRADICT", "STRONG", "Forty steps up from the street."),
        ], lift=None, step=False, bath=None, walking="HIGH", rating=4.8, diets=["GLUTEN_FREE"]),
    ],
    "Christchurch": [
        stay("CHC_GARDEN", "Botanic Gardens Suites", "890.00", GENTLE,
             verified("Lift serves both guest floors.", "Level entry and wide doors.", "Roll-in shower and grab rails."),
             lift=True, step=True, bath=True, walking="LOW", rating=4.6, diets=EVERY_DIET, transfer=True),
        stay("CHC_CITY", "Riverside City Hotel", "830.00", WEEK, [
            (LIFT, "official_amenity", "SUPPORT", "STRONG", "Lifts to all floors."),
            (STEP, "official_amenity", "SUPPORT", "STRONG", "Level entry."),
            (BATH, "official_amenity", "UNKNOWN", "WEAK", "Accessible bathroom 'on request'."),
        ], lift=True, step=True, bath=None, walking="MODERATE", rating=4.3, diets=["VEGETARIAN", "HALAL"]),
        stay("CHC_VILLA", "Merivale Villa Stay", "760.00", STRICT, [
            (STEP, "accessibility_audit", "CONTRADICT", "STRONG", "Two steps at the entrance and between rooms."),
        ], lift=None, step=False, bath=None, walking="MODERATE", rating=4.4, diets=["VEGETARIAN"]),
    ],
    "Taupō": [
        stay("TPO_LAKE", "Lake Taupō Accessible Resort", "950.00", GENTLE,
             verified("Single-level rooms and a lift to the restaurant.", "Level entry throughout.", "Roll-in showers in every accessible room."),
             lift=True, step=True, bath=True, walking="LOW", rating=4.5, diets=EVERY_DIET, transfer=True),
        stay("TPO_LODGE", "Huka Falls Lodge", "990.00", STRICT, [
            (LIFT, "official_amenity", "UNKNOWN", "WEAK", "Lift coverage of the garden wing is not stated."),
            (STEP, "official_amenity", "SUPPORT", "STRONG", "Ramp from the car park."),
            (BATH, "official_amenity", "SUPPORT", "WEAK", "One room is described as 'accessible'."),
        ], lift=None, step=True, bath=None, walking="LOW", rating=4.8, diets=["VEGETARIAN", "GLUTEN_FREE", "SOFT_FOOD"]),
        stay("TPO_MOTEL", "Town Motel", "640.00", WEEK, [
            (LIFT, "official_amenity", "CONTRADICT", "STRONG", "Upstairs units have no lift."),
            (STEP, "official_amenity", "CONTRADICT", "STRONG", "A kerb and step at every unit."),
        ], lift=False, step=False, bath=False, walking="MODERATE", rating=4.0, diets=[]),
    ],
}


def evidence_rows(product: dict) -> list[dict]:
    rows = []
    for index, row in enumerate(product["evidence"], 1):
        claim, source, polarity, strength, detail = row[:5]
        reference = row[5] if len(row) > 5 else f"{product['product_id']}-{index}"
        rows.append({"claim_type": claim, "source": source, "polarity": polarity, "strength": strength,
                     "reference": reference, "detail": detail, "url": f"https://supplier.example/evidence/{reference}"})
    return rows
