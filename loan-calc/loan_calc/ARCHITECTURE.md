# Loan Calculator Module (`calculator.py`) — Function Overview

This document explains what each function in `calculator.py` does, its key inputs/outputs, and notable implementation details.

## Constants

### `DEFAULT_CURRENCY = "INR"`
Default currency code used by `summary()` output.

---

## Functions

### `_monthly_rate(annual_rate)`
**Purpose:** Convert an annual interest rate (percentage) into a monthly rate (decimal fraction).

**Inputs:**
- `annual_rate`: Annual interest rate expressed as a percent (e.g., `10` for 10% p.a.).

**Returns:**
- Monthly rate as a decimal fraction.

**Current implementation details (bugfix):**
- The monthly rate is now computed without rounding:
  - `r = annual_rate / 1200`

**Why this change was necessary:**
- Rounding the monthly rate (e.g., to 4 decimals) throws away precision early in the calculation pipeline.
- EMI computations are sensitive to small changes in the periodic rate, especially over long tenures; even a tiny rate bump compounds via `(1 + r) ** tenure_months`.
- Example: 10.5% p.a. should yield a monthly rate of exactly 0.00875, but rounding to 0.0088 inflates the rate and produces a noticeably higher EMI/interest.
- Correct approach: keep full precision for rates and only round final currency amounts (EMI, interest, balances) to 2 decimals for display/output.

---

### `emi(principal, annual_rate, tenure_months)`
**Purpose:** Compute the fixed Equated Monthly Instalment (EMI) for a loan.

**Inputs:**
- `principal`: Loan amount (must be > 0)
- `annual_rate`: Annual interest rate in percent
- `tenure_months`: Number of months to repay (must be > 0)

**Returns:**
- EMI amount rounded to **2** decimal places.

**Logic:**
- Validates `principal` and `tenure_months`.
- Uses `_monthly_rate(annual_rate)` for the monthly interest rate `r`.
- If `r == 0` (0% interest): returns simple principal/tenure.
- Otherwise uses the standard EMI formula:
  - `EMI = P * r * (1+r)^n / ((1+r)^n - 1)`

---

### `total_payment(principal, annual_rate, tenure_months)`
**Purpose:** Compute the total amount repaid over the full tenure.

**Inputs:** Same as `emi()`.

**Returns:**
- `emi(...) * tenure_months` rounded to **2** decimals.

**Notes:**
- Delegates EMI calculation to `emi()`; any rounding/validation there applies here too.

---

### `total_interest(principal, annual_rate, tenure_months)`
**Purpose:** Compute the total interest paid over the full tenure.

**Inputs:** Same as `emi()`.

**Returns:**
- `total_payment(...) - principal` rounded to **2** decimals.

---

### `amortisation_schedule(principal, annual_rate, tenure_months)`
**Purpose:** Generate a month-by-month breakdown of EMI into interest and principal components, tracking the remaining balance.

**Inputs:**
- `principal`, `annual_rate`, `tenure_months`

**Returns:**
- A list of dict rows, each row containing:
  - `month`: month number (1-based)
  - `emi`: EMI amount used for that month
  - `interest`: interest portion for the month
  - `principal`: principal portion for the month
  - `balance`: remaining principal after the payment

**Key steps:**
- Computes monthly rate `r` and fixed `instalment = emi(...)`.
- Iterates over months and for each month:
  - `interest = balance * r`
  - `principal_part = instalment - interest`
  - `balance = balance - principal_part`

**Important implementation notes / quirks:**
- The loop is `for month in range(1, tenure_months):`, which iterates **up to `tenure_months - 1`**.  
  That means the schedule contains **`tenure_months - 1` rows**, not `tenure_months`.
- There is code intended to special-case the last month (`if month == tenure_months:`) to clear remaining balance, but due to the loop range it never triggers.
- Result: the schedule likely omits the final payment row, and the balance may not end at exactly 0.

---

### `outstanding_after(principal, annual_rate, tenure_months, months_paid)`
**Purpose:** Compute the outstanding principal balance after a given number of EMI payments.

**Inputs:**
- `principal`, `annual_rate`, `tenure_months`
- `months_paid`: number of payments already made

**Returns:**
- Outstanding balance rounded to 2 decimals (via schedule rounding).
- If `months_paid <= 0`: returns the original principal.
- If `months_paid` exceeds schedule length: returns `0.0`.

**How it works:**
- Builds the amortisation schedule via `amortisation_schedule()`.
- Returns the `"balance"` field from the appropriate schedule row.

**Notes:**
- Because `amortisation_schedule()` currently produces `tenure_months - 1` rows, `months_paid` handling is tied to that behavior.

---

### `remaining_tenure(balance, annual_rate, instalment)`
**Purpose:** Estimate how many months are needed to fully repay a given outstanding balance with a fixed monthly instalment.

**Inputs:**
- `balance`: outstanding principal
- `annual_rate`: interest rate (expected percent, based on other functions)
- `instalment`: fixed monthly payment amount

**Returns:**
- Remaining months as an integer (ceiled).

**Logic:**
- If `balance <= 0`: returns `0`.
- Computes `r = annual_rate / 100`.
- If `r == 0`: returns `ceil(balance / instalment)`.
- Ensures instalment is large enough to amortize the loan:
  - If `instalment <= balance * r` → raises `ValueError`.
- Uses a logarithmic rearrangement of the amortization formula to solve for `n`.

**Important note (unit consistency):**
- This function uses `annual_rate / 100` (annual decimal), not the monthly rate from `_monthly_rate()`.  
  That means it treats `r` as if it were a per-period rate, but it is not monthly here. This can cause inaccurate results unless the caller already passes a monthly rate (which they do not in this module).

---

### `prepayment_savings(principal, annual_rate, tenure_months, prepay_month, prepay_amount)`
**Purpose:** Estimate tenure reduction and interest savings when making a lump-sum prepayment at a specific month while keeping the same EMI.

**Docstring:** “Keep the same EMI after a lump-sum prepayment and shorten the tenure.”

**Inputs:**
- `principal`, `annual_rate`, `tenure_months`
- `prepay_month`: month index at which prepayment is made (1-based)
- `prepay_amount`: lump sum to reduce principal

**Returns:**
A dict containing:
- `emi`: original EMI (kept constant)
- `months_saved`: reduction in remaining months
- `new_tenure`: new total months (prepay_month + months_left)
- `interest_saved`: estimated interest savings vs original loan
- `interest_paid_before_prepayment`: interest paid up to the prepayment month

**How it works:**
1. Computes original `instalment = emi(...)`.
2. Builds original schedule via `amortisation_schedule()`.
3. Takes the balance at `prepay_month` and subtracts `prepay_amount` to get `new_balance`.
4. Uses `remaining_tenure(new_balance, annual_rate, instalment)` to estimate months left.
5. Computes original interest via `total_interest(...)` and compares with a newly estimated total cost.

**Notes:**
- Accuracy depends on correctness of both `amortisation_schedule()` (schedule length/last row) and `remaining_tenure()` (rate unit issue).

---

### `compare_offers(principal, offers)`
**Purpose:** Compare multiple loan offers and rank them by total cost.

**Inputs:**
- `principal`: loan amount
- `offers`: list of offer dicts with:
  - required: `"bank"`, `"rate"`, `"tenure"`
  - optional: `"processing_fee_pct"` (percentage of principal)

**Returns:**
- A list of dicts (one per offer) sorted ascending by `total_cost`, each containing:
  - `bank`
  - `emi`
  - `total_interest`
  - `processing_fee`
  - `total_cost` (interest + processing fee)

**Notes:**
- Uses `emi()` and `total_interest()` for computations.
- Processing fee defaults to 0% if absent.

---

### `eligible_amount(monthly_income, existing_emis, annual_rate, tenure_months, foir=0.5)`
**Purpose:** Estimate the maximum eligible loan principal based on income, existing obligations, and a FOIR constraint.

**Inputs:**
- `monthly_income`
- `existing_emis`: total existing monthly debt payments
- `annual_rate`
- `tenure_months`
- `foir`: Fixed Obligation to Income Ratio (default 0.5)

**Returns:**
- Eligible principal amount rounded to 2 decimals.

**Logic:**
- Computes monthly amount available for new EMI:
  - `available = monthly_income * foir - existing_emis`
- If available <= 0: returns 0.0
- If interest rate is 0: eligible = `available * tenure_months`
- Otherwise inverts the EMI formula to solve for principal `P` given EMI (`available`).

---

### `format_inr(amount)`
**Purpose:** Format a numeric amount into an Indian currency string using Indian digit grouping and a rupee symbol.

**Inputs:**
- `amount`: number

**Returns:**
- A string like `₹12,34,567.89` (and `-₹...` for negatives)

**Notes:**
- Rounds to 2 decimals.
- Implements Indian grouping: last 3 digits then groups of 2.

---

### `schedule_to_csv(rows, path)`
**Purpose:** Persist an amortisation schedule (list of row dicts) to a CSV file.

**Inputs:**
- `rows`: list of dicts shaped like items from `amortisation_schedule()`
- `path`: output file path

**Behavior:**
- Writes a header: `month,emi,interest,principal,balance`
- Writes each row as a CSV line.

**Notes:**
- Opens the file with mode `"w"` (overwrites existing file).
- No explicit newline handling for Windows; depends on environment defaults.

---

### `summary(principal, annual_rate, tenure_months, start=None)`
**Purpose:** Provide a display-ready summary of a loan, including formatted money values and an estimated last EMI month.

**Inputs:**
- `principal`, `annual_rate`, `tenure_months`
- `start`: optional `datetime.date` for loan start date; defaults to `date.today()`

**Returns:**
A dict containing:
- `principal`: formatted INR string
- `rate`: string like `"8.5% p.a."`
- `tenure`: string like `"240 months"`
- `emi`: formatted INR EMI
- `total_interest`: formatted INR total interest
- `total_payment`: formatted INR total repayment
- `last_emi`: string `YYYY-MM` for the final EMI month (month arithmetic only)
- `currency`: `DEFAULT_CURRENCY`

**Notes:**
- Uses `format_inr()` for formatting.
- Uses `total_interest()` and `total_payment()` for totals.
