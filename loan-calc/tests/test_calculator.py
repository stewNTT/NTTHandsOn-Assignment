import math
from datetime import date

import pytest

from loan_calc import calculator
from loan_calc.exceptions import (
    InsufficientInstalmentError,
    InvalidInputError,
    PrepaymentError,
)


# ----------------------------
# 1) Seeded-bug regression tests
# ----------------------------

def test_rounding_bug_emi_10_5pct_240m_spreadsheet_reference():
    """
    Regression: rounding the monthly rate to 4 decimals skews EMI for some rates.

    10.5% p.a. -> monthly 0.00875; the buggy code rounds it to 0.0088 (EMI ~10,024).
    Expected EMI from an independent spreadsheet formula:
        =PMT(10.5%/12, 240, -1000000)  ->  9,983.80
    """
    expected = 9983.80
    got = calculator.emi(1_000_000, 10.5, 240)
    assert abs(got - expected) <= 1


def test_schedule_length_bug_12_months_produces_12_rows():
    """Regression: a 12-month loan must produce 12 rows (months 1..12)."""
    schedule = calculator.amortisation_schedule(100000, 9, 12)
    assert len(schedule) == 12
    assert [r["month"] for r in schedule] == list(range(1, 13))


def test_units_bug_remaining_tenure_uses_monthly_rate():
    """
    Regression: remaining_tenure must use the monthly rate (annual / 1200).

    balance=100000, 12% p.a. -> 1% per month, instalment=2000
    n = -ln(1 - 0.5) / ln(1.01) = 69.66 -> 70 months.
    """
    assert calculator.remaining_tenure(100000, 12, 2000) == 70


def test_prepayment_new_tenure_matches_rebuilt_schedule_length():
    """
    After a prepayment, the reported new_tenure must match a month-by-month
    simulation of the reduced balance at the same EMI.
    """
    principal, annual_rate, tenure_months = 1_000_000, 9, 240
    prepay_month, prepay_amount = 12, 100_000

    result = calculator.prepayment_savings(
        principal, annual_rate, tenure_months, prepay_month, prepay_amount
    )

    sched = calculator.amortisation_schedule(principal, annual_rate, tenure_months)
    balance = sched[prepay_month - 1]["balance"] - prepay_amount
    r = annual_rate / 1200
    months = 0
    while balance > 0.005:
        balance = balance * (1 + r) - result["emi"]
        months += 1

    assert result["new_tenure"] == prepay_month + months
    assert result["months_saved"] == (tenure_months - prepay_month) - months
    assert result["interest_saved"] > 0


# ----------------------------
# 2) Schedule invariants
# ----------------------------

def test_schedule_principal_sums_to_loan_amount():
    schedule = calculator.amortisation_schedule(500_000, 9, 60)
    assert abs(sum(r["principal"] for r in schedule) - 500_000) <= 0.01


def test_schedule_interest_sums_to_total_interest():
    """
    Rows are rounded to 2 decimals each and the last row absorbs the residue,
    so the sum drifts slightly from total_interest. Allow ₹1, not ₹0.01.
    """
    schedule = calculator.amortisation_schedule(500_000, 9, 60)
    interest_sum = sum(r["interest"] for r in schedule)
    expected = calculator.total_interest(500_000, 9, 60)
    assert abs(interest_sum - expected) <= 1.0


def test_schedule_last_balance_is_zero():
    schedule = calculator.amortisation_schedule(250_000, 9, 24)
    assert schedule[-1]["balance"] == 0.0


def test_schedule_first_row_interest():
    # 1,00,000 at 12% -> first month's interest is exactly 1% = 1,000.00
    schedule = calculator.amortisation_schedule(100_000, 12, 12)
    assert schedule[0]["interest"] == 1000.00


# ----------------------------
# 3) Required edge cases
# ----------------------------

def test_emi_zero_interest():
    assert calculator.emi(120000, 0, 12) == 10000.00


def test_total_interest_and_payment_zero_interest():
    assert calculator.total_interest(500000, 0, 50) == 0.00
    assert calculator.total_payment(500000, 0, 50) == 500000.00


def test_zero_interest_schedule_has_zero_interest_each_row():
    schedule = calculator.amortisation_schedule(120000, 0, 12)
    assert all(r["interest"] == 0.0 for r in schedule)
    assert schedule[-1]["balance"] == 0.0


def test_one_month_tenure_emi_with_interest():
    # 1 month at 12% p.a.: pay principal + 1% interest in a single instalment
    assert calculator.emi(250000, 12, 1) == 252500.00


def test_one_month_schedule_single_row_and_zero_balance():
    schedule = calculator.amortisation_schedule(250000, 12, 1)
    assert len(schedule) == 1
    assert schedule[0]["interest"] == 2500.00
    assert schedule[0]["balance"] == 0.0


def test_very_large_principal_100_crore():
    principal = 100_00_00_000.0  # ₹100 crore
    e = calculator.emi(principal, 9.0, 240)
    # EMI scales linearly with principal: 1000x the 10-lakh reference
    assert abs(e - 8_997_259.56) <= 1
    schedule = calculator.amortisation_schedule(principal, 9.0, 240)
    assert len(schedule) == 240
    assert schedule[-1]["balance"] == 0.0


def test_prepayment_larger_than_remaining_balance():
    principal, annual_rate, tenure_months, prepay_month = 1_000_000, 9, 240, 12
    sched = calculator.amortisation_schedule(principal, annual_rate, tenure_months)
    remaining_balance = sched[prepay_month - 1]["balance"]

    with pytest.raises(PrepaymentError):
        calculator.prepayment_savings(
            principal, annual_rate, tenure_months, prepay_month, remaining_balance + 1.0
        )


def test_emi_reference_check_10_lakh_9pct_240_months():
    # Acceptance criterion: ₹10,00,000 at 9% p.a. over 240 months ≈ ₹8,997 (±1)
    assert abs(calculator.emi(1_000_000, 9, 240) - 8997) <= 1


# ----------------------------
# 4) Error paths
# ----------------------------

@pytest.mark.parametrize("principal, tenure", [(0, 12), (-1000, 12), (100000, 0), (100000, -5)])
def test_emi_rejects_non_positive_inputs(principal, tenure):
    with pytest.raises(InvalidInputError):
        calculator.emi(principal, 9, tenure)


def test_remaining_tenure_instalment_too_small():
    # 1% of 1,00,000 = 1,000 interest per month; 500 never repays it
    with pytest.raises(InsufficientInstalmentError):
        calculator.remaining_tenure(100000, 12, 500)


def test_remaining_tenure_zero_balance():
    assert calculator.remaining_tenure(0, 12, 2000) == 0


def test_remaining_tenure_zero_interest():
    assert calculator.remaining_tenure(10000, 0, 1000) == 10
    assert calculator.remaining_tenure(10001, 0, 1000) == 11


# ----------------------------
# 5) outstanding_after
# ----------------------------

def test_outstanding_after_zero_and_negative_months():
    assert calculator.outstanding_after(100000, 12, 12, 0) == 100000.00
    assert calculator.outstanding_after(100000, 12, 12, -3) == 100000.00


def test_outstanding_after_one_month_matches_formula():
    # P*(1+r) - EMI = 100000*1.01 - 8884.88 = 92115.12
    assert calculator.outstanding_after(100000, 12, 12, 1) == 92115.12


def test_outstanding_after_full_and_beyond_tenure():
    assert calculator.outstanding_after(100000, 12, 12, 12) == 0.0
    assert calculator.outstanding_after(100000, 12, 12, 50) == 0.0


# ----------------------------
# 6) compare_offers
# ----------------------------

def test_compare_offers_sorted_by_total_cost():
    offers = [
        {"bank": "A", "rate": 10, "tenure": 60},
        {"bank": "B", "rate": 8, "tenure": 60},
        {"bank": "C", "rate": 9, "tenure": 60},
    ]
    result = calculator.compare_offers(500000, offers)
    assert [o["bank"] for o in result] == ["B", "C", "A"]
    costs = [o["total_cost"] for o in result]
    assert costs == sorted(costs)


def test_compare_offers_processing_fee_can_change_ranking():
    offers = [
        {"bank": "LowRateHighFee", "rate": 8.0, "tenure": 60, "processing_fee_pct": 5},
        {"bank": "HigherRateNoFee", "rate": 8.5, "tenure": 60},
    ]
    result = calculator.compare_offers(500000, offers)
    assert result[0]["bank"] == "HigherRateNoFee"
    assert result[1]["processing_fee"] == 25000.00
    assert result[1]["total_cost"] == round(result[1]["total_interest"] + 25000, 2)


def test_compare_offers_missing_fee_defaults_to_zero():
    result = calculator.compare_offers(100000, [{"bank": "X", "rate": 9, "tenure": 12}])
    assert result[0]["processing_fee"] == 0.0
    assert result[0]["total_cost"] == result[0]["total_interest"]


def test_compare_offers_empty_list():
    assert calculator.compare_offers(100000, []) == []


# ----------------------------
# 7) eligible_amount
# ----------------------------

def test_eligible_amount_zero_when_no_headroom():
    # 50% of 40,000 = 20,000; existing EMIs already use 20,000
    assert calculator.eligible_amount(40000, 20000, 9, 240) == 0.0
    assert calculator.eligible_amount(40000, 25000, 9, 240) == 0.0


def test_eligible_amount_zero_interest():
    # available = 100000*0.5 - 10000 = 40000; 40000 * 12 = 480000
    assert calculator.eligible_amount(100000, 10000, 0, 12) == 480000.00


def test_eligible_amount_round_trips_through_emi():
    # available = 60000*0.5 - 5000 = 25000
    amount = calculator.eligible_amount(60000, 5000, 9, 240)
    assert abs(amount - 2_778_623.85) <= 1
    assert abs(calculator.emi(amount, 9, 240) - 25000) <= 1


# ----------------------------
# 8) format_inr
# ----------------------------

@pytest.mark.parametrize(
    "amount, expected",
    [
        (0, "₹0.00"),
        (999.5, "₹999.50"),
        (1000, "₹1,000.00"),
        (100000, "₹1,00,000.00"),
        (1234567.891, "₹12,34,567.89"),
        (1_000_000_000, "₹1,00,00,00,000.00"),
        (-5000, "-₹5,000.00"),
    ],
)
def test_format_inr(amount, expected):
    assert calculator.format_inr(amount) == expected


# ----------------------------
# 9) schedule_to_csv
# ----------------------------

def test_schedule_to_csv_writes_header_and_rows(tmp_path):
    rows = calculator.amortisation_schedule(100000, 12, 12)
    out = tmp_path / "schedule.csv"
    calculator.schedule_to_csv(rows, str(out))

    lines = out.read_text().splitlines()
    assert lines[0] == "month,emi,interest,principal,balance"
    assert len(lines) == 13  # header + 12 months
    first = lines[1].split(",")
    assert first[0] == "1"
    assert float(first[2]) == 1000.00
    assert float(lines[-1].split(",")[4]) == 0.0


# ----------------------------
# 10) summary
# ----------------------------

def test_summary_fields_with_fixed_start_date():
    s = calculator.summary(1_000_000, 9, 240, start=date(2026, 1, 15))
    assert s["principal"] == "₹10,00,000.00"
    assert s["rate"] == "9% p.a."
    assert s["tenure"] == "240 months"
    assert s["emi"] == "₹8,997.26"
    assert s["currency"] == "INR"
    assert s["total_payment"] == calculator.format_inr(
        calculator.total_payment(1_000_000, 9, 240)
    )
    assert s["total_interest"] == calculator.format_inr(
        calculator.total_interest(1_000_000, 9, 240)
    )


def test_summary_defaults_start_to_today():
    s = calculator.summary(100000, 9, 12)
    assert len(s["last_emi"]) == 7 and s["last_emi"][4] == "-"


# ----------------------------
# 11) Validation error-path coverage (to reach 100%)
# ----------------------------

@pytest.mark.parametrize(
    "principal, annual_rate, tenure_months, msg",
    [
        ("100000", 9, 12, "principal must be a number"),
        (100000, "9", 12, "annual_rate must be a number"),
        (100000, -1, 12, "annual_rate cannot be negative"),
        (0, 9, 12, "principal must be positive"),
        (-100, 9, 12, "principal must be positive"),
    ],
)
def test_emi_invalid_principal_or_rate_types_and_bounds(principal, annual_rate, tenure_months, msg):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.emi(principal, annual_rate, tenure_months)


@pytest.mark.parametrize(
    "tenure_months, msg",
    [
        (12.0, "tenure_months must be an int"),
        ("12", "tenure_months must be an int"),
        (0, "tenure_months must be positive"),
        (-5, "tenure_months must be positive"),
    ],
)
def test_emi_invalid_tenure_type_and_bounds(tenure_months, msg):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.emi(100000, 9, tenure_months)


def test_outstanding_after_months_paid_must_be_int():
    with pytest.raises(InvalidInputError, match="months_paid must be an int"):
        calculator.outstanding_after(100000, 12, 12, "1")


@pytest.mark.parametrize(
    "balance, annual_rate, instalment, msg",
    [
        ("100000", 12, 2000, "balance must be a number"),
        (100000, "12", 2000, "annual_rate must be a number"),
        (100000, -1, 2000, "annual_rate cannot be negative"),
        (100000, 12, "2000", "instalment must be a number"),
        (100000, 12, 0, "instalment must be positive"),
        (100000, 12, -10, "instalment must be positive"),
    ],
)
def test_remaining_tenure_validation_errors(balance, annual_rate, instalment, msg):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.remaining_tenure(balance, annual_rate, instalment)


@pytest.mark.parametrize(
    "prepay_month, prepay_amount, msg",
    [
        ("12", 1000, "prepay_month must be an int"),
        (0, 1000, "prepay_month must be within 1..tenure_months"),
        (241, 1000, "prepay_month must be within 1..tenure_months"),
        (12, "1000", "prepay_amount must be a number"),
        (12, 0, "prepay_amount must be positive"),
        (12, -1, "prepay_amount must be positive"),
    ],
)
def test_prepayment_savings_invalid_month_or_amount(prepay_month, prepay_amount, msg):
    with pytest.raises(PrepaymentError, match=msg):
        calculator.prepayment_savings(1_000_000, 9, 240, prepay_month, prepay_amount)


def test_prepayment_equal_to_remaining_balance_closes_loan():
    principal, annual_rate, tenure_months, prepay_month = 1_000_000, 9, 240, 12
    sched = calculator.amortisation_schedule(principal, annual_rate, tenure_months)
    remaining_balance = sched[prepay_month - 1]["balance"]

    result = calculator.prepayment_savings(
        principal, annual_rate, tenure_months, prepay_month, remaining_balance
    )
    assert result["new_tenure"] == prepay_month


@pytest.mark.parametrize(
    "principal, offers, msg",
    [
        ("500000", [{"bank": "A", "rate": 9, "tenure": 12}], "principal must be a number"),
        (-1, [{"bank": "A", "rate": 9, "tenure": 12}], "principal must be positive"),
        (500000, "not-a-list", "offers must be a list of dicts"),
    ],
)
def test_compare_offers_invalid_top_level_inputs(principal, offers, msg):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.compare_offers(principal, offers)


@pytest.mark.parametrize(
    "offers, msg",
    [
        ([1], "each offer must be a dict"),
        ([{"bank": "A", "tenure": 12}], "offer missing required key: rate"),
        ([{"rate": 9, "tenure": 12}], "offer missing required key: bank"),
        ([{"bank": "A", "rate": 9}], "offer missing required key: tenure"),
    ],
)
def test_compare_offers_invalid_offer_items(offers, msg):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.compare_offers(500000, offers)


@pytest.mark.parametrize(
    "monthly_income, existing_emis, annual_rate, tenure_months, foir, msg",
    [
        ("100000", 10000, 9, 240, 0.5, "monthly_income must be a number"),
        (100000, "10000", 9, 240, 0.5, "existing_emis must be a number"),
        (100000, 10000, 9, 240, "0.5", "foir must be a number"),
        (-1, 0, 9, 240, 0.5, "monthly_income cannot be negative"),
        (100000, -1, 9, 240, 0.5, "existing_emis cannot be negative"),
        (100000, 0, -1, 240, 0.5, "annual_rate cannot be negative"),
        (100000, 0, "9", 240, 0.5, "annual_rate must be a number"),
        (100000, 0, 9, "240", 0.5, "tenure_months must be an int"),
        (100000, 0, 9, 0, 0.5, "tenure_months must be positive"),
        (100000, 0, 9, -1, 0.5, "tenure_months must be positive"),
        (100000, 0, 9, 240, -0.1, "foir must be between 0 and 1"),
        (100000, 0, 9, 240, 1.1, "foir must be between 0 and 1"),
    ],
)
def test_eligible_amount_validation_errors(
    monthly_income, existing_emis, annual_rate, tenure_months, foir, msg
):
    with pytest.raises(InvalidInputError, match=msg):
        calculator.eligible_amount(monthly_income, existing_emis, annual_rate, tenure_months, foir)
