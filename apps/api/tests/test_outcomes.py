"""Unit tests for Foundation outcomes aggregation + k-anonymity."""
from app.skilled_pro import outcomes


def _row(program, placed, wage=None, ttoh=None, creds=0):
    return {
        "program": program, "region": "GA", "cohort_year": 2025,
        "placed": placed, "wage": wage, "time_to_hire_days": ttoh,
        "credential_count": creds, "verified_credential_count": creds,
    }


ROWS = [
    _row("Welding", True, 52000, 90, 1),
    _row("Welding", True, 56000, 120, 1),
    _row("Welding", False, None, None, 0),
    _row("HVAC", True, 60000, 60, 1),
    _row("HVAC", False, None, None, 1),
]


def test_rate_and_median():
    assert outcomes.rate(2, 4) == 0.5
    assert outcomes.rate(0, 0) is None
    assert outcomes.median_int([52000, 56000]) == 54000
    assert outcomes.median_int([None, None]) is None


def test_overall_summary():
    s = outcomes.overall_summary(ROWS)
    assert s["total_served"] == 5
    assert s["placed"] == 3
    assert s["employment_rate"] == 0.6          # 3/5
    assert s["median_wage"] == 56000            # median of 52k,56k,60k
    assert s["attainment_rate"] == 0.8          # 4 of 5 have a credential


def test_aggregate_cohorts_sorted_and_correct():
    cohorts = outcomes.aggregate_cohorts(ROWS, "program")
    assert [c["cohort"] for c in cohorts] == ["Welding", "HVAC"]   # size desc
    welding = cohorts[0]
    assert welding["n"] == 3 and welding["placed"] == 2
    assert welding["employment_rate"] == 0.667
    assert welding["median_wage"] == 54000
    assert welding["median_time_to_hire_days"] == 105


def test_k_anonymity_suppresses_small_cohorts():
    cohorts = outcomes.aggregate_cohorts(ROWS, "program")
    feed = outcomes.apply_k_anonymity(cohorts, k=10)
    # Both cohorts are < 10 -> suppressed, metrics nulled, count still disclosed.
    for c in feed:
        assert c["suppressed"] is True
        assert c["employment_rate"] is None
        assert c["median_wage"] is None
        assert "n" in c


def test_k_anonymity_allows_large_cohorts():
    big = [_row("Welding", i % 2 == 0, 50000 if i % 2 == 0 else None) for i in range(12)]
    feed = outcomes.apply_k_anonymity(outcomes.aggregate_cohorts(big, "program"), k=10)
    assert feed[0]["suppressed"] is False
    assert feed[0]["employment_rate"] is not None


def test_impact_report_template_is_grounded():
    from app.skilled_pro.ai import template_impact_report
    numbers = {
        "summary": outcomes.overall_summary(ROWS),
        "top_programs": outcomes.aggregate_cohorts(ROWS, "program")[:1],
    }
    text = template_impact_report(numbers)
    assert "5 learners" in text          # total_served
    assert "$56,000" in text             # median wage formatted
    assert "Welding" in text             # leading cohort
    assert "60%" in text                 # employment rate
