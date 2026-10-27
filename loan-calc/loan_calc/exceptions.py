"""Exception hierarchy for loan_calc.
 
These exceptions are used by `loan_calc.calculator` for input validation and
error reporting.
"""
 
 
class LoanCalculatorError(Exception):
    """Base exception for all loan calculator errors."""
 
 
class InvalidInputError(LoanCalculatorError):
    """Raised when an input is invalid.
 
    Examples:
    - wrong type (e.g. None, strings where numbers expected)
    - non-positive principal
    - negative interest rate
    - non-positive tenure
    """
 
 
class InsufficientInstalmentError(LoanCalculatorError):
    """Raised when an instalment is too small to cover monthly interest."""
 
 
class PrepaymentError(LoanCalculatorError):
    """Raised when prepayment inputs are invalid.
 
    Examples:
    - prepay_month out of range
    - prepay_amount non-positive
    - prepay_amount exceeds the outstanding balance at the prepayment month
    """
