"""
citecheck.utils.safe_math
-------------------------
Deterministic and safe arithmetic expression evaluator using Python's `ast` module and `Decimal`.
Strictly avoids `eval()` and `exec()`.

Supported:
- Binary operations: Addition (+), Subtraction (-), Multiplication (*), Division (/)
- Unary operations: Positive (+x), Negation (-x)
- Grouping: Parentheses ()
- Operands: Finite numeric constants (integers and floats converted to Decimal)

Security and safety guarantees:
- Rejects function calls, variable names, attributes, imports, booleans, and bitwise operators.
- Enforces maximum expression length limit (MAX_EXPRESSION_LENGTH).
- Enforces AST node count limit (MAX_AST_NODES) and nesting depth limit (MAX_AST_DEPTH).
- Rejects non-finite values (Infinity, -Infinity, NaN).
- Traps division by zero, decimal overflow, underflow, and arithmetic errors, converting
  them into controlled SafeMathError subclasses.
- Zero reliance on arbitrary code execution.
"""

import ast
from decimal import Decimal, DecimalException, DivisionByZero, InvalidOperation
import math

# Safety Limits
MAX_EXPRESSION_LENGTH: int = 1000
MAX_AST_NODES: int = 100
MAX_AST_DEPTH: int = 20


class SafeMathError(Exception):
    """Base exception for all safe math evaluation errors."""
    pass


class SafeDivisionByZeroError(SafeMathError):
    """Raised when an expression attempts to divide by zero."""
    pass


class SafeArithmeticError(SafeMathError):
    """Raised when an arithmetic computation fails (e.g., overflow, underflow, or non-finite result)."""
    pass


class UnsafeExpressionError(SafeMathError):
    """Raised when an expression contains unauthorized syntax, variables, calls, non-finite values, or exceeds complexity limits."""
    pass


# Map allowed AST binary operators to their computation functions
_ALLOWED_BINARY_OPS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: _safe_divide(left, right),
}

# Map allowed AST unary operators to their computation functions
_ALLOWED_UNARY_OPS = {
    ast.UAdd: lambda operand: +operand,
    ast.USub: lambda operand: -operand,
}


def _safe_divide(left: Decimal, right: Decimal) -> Decimal:
    """Perform division with explicit zero-check protection."""
    if right == Decimal(0):
        raise SafeDivisionByZeroError("Division by zero is not permitted.")
    try:
        return left / right
    except DivisionByZero:
        raise SafeDivisionByZeroError("Division by zero is not permitted.")


def _check_ast_depth(node: ast.AST, current_depth: int = 1) -> None:
    """Verify that AST nesting depth does not exceed MAX_AST_DEPTH."""
    if current_depth > MAX_AST_DEPTH:
        raise UnsafeExpressionError(
            f"Expression exceeds maximum nesting depth of {MAX_AST_DEPTH}."
        )
    for child in ast.iter_child_nodes(node):
        _check_ast_depth(child, current_depth + 1)


def _eval_ast_node(node: ast.AST) -> Decimal:
    """
    Recursively evaluate an AST node.
    Only allows Constants (finite numbers), BinOp (+, -, *, /), and UnaryOp (+, -).
    """
    # 1. Numeric Constants (e.g., 42, 3.14, 0.20)
    if isinstance(node, ast.Constant):
        # In Python, bool is a subclass of int (isinstance(True, int) == True).
        # We must explicitly reject booleans.
        if isinstance(node.value, bool):
            raise UnsafeExpressionError("Booleans (True/False) are not permitted as numeric constants.")

        # Check for non-finite float constants (e.g., 1e309 which evaluates to inf)
        if isinstance(node.value, float) and (math.isinf(node.value) or math.isnan(node.value)):
            raise UnsafeExpressionError("Non-finite numbers (Infinity/NaN) are not permitted.")

        if isinstance(node.value, (int, float)):
            try:
                # Convert via string to avoid float precision artifacts
                val = Decimal(str(node.value))
            except (InvalidOperation, DecimalException, ValueError):
                raise UnsafeExpressionError(f"Invalid numeric value: {node.value}")

            # Double check Decimal finiteness
            if not val.is_finite():
                raise UnsafeExpressionError("Non-finite numbers (Infinity/NaN) are not permitted.")

            return val

        raise UnsafeExpressionError(f"Unsupported constant type: {type(node.value).__name__}. Only numbers are allowed.")

    # 2. Binary Operations (e.g., left + right, left * right)
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPS:
            raise UnsafeExpressionError(f"Unsupported operator: {op_type.__name__}. Allowed operators: +, -, *, /.")

        left_val = _eval_ast_node(node.left)
        right_val = _eval_ast_node(node.right)
        op_func = _ALLOWED_BINARY_OPS[op_type]

        try:
            result = op_func(left_val, right_val)
        except SafeDivisionByZeroError:
            raise
        except DivisionByZero:
            raise SafeDivisionByZeroError("Division by zero is not permitted.")
        except (DecimalException, OverflowError, ArithmeticError) as e:
            raise SafeArithmeticError(f"Arithmetic computation error: {e}")

        if not result.is_finite():
            raise SafeArithmeticError("Computation resulted in a non-finite value (Infinity or NaN).")

        return result

    # 3. Unary Operations (e.g., -5, +10)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPS:
            raise UnsafeExpressionError(f"Unsupported unary operator: {op_type.__name__}. Allowed: +, -.")

        operand_val = _eval_ast_node(node.operand)
        op_func = _ALLOWED_UNARY_OPS[op_type]

        try:
            result = op_func(operand_val)
        except (DecimalException, OverflowError, ArithmeticError) as e:
            raise SafeArithmeticError(f"Arithmetic computation error: {e}")

        if not result.is_finite():
            raise SafeArithmeticError("Computation resulted in a non-finite value (Infinity or NaN).")

        return result

    # 4. Any other AST node (Call, Name, Attribute, Subscript, Import, etc.)
    else:
        raise UnsafeExpressionError(
            f"Unauthorized expression element '{type(node).__name__}'. "
            "Only arithmetic expressions with numbers, +, -, *, /, and parentheses are allowed."
        )


def evaluate_expression(expression: str) -> Decimal:
    """
    Safely evaluate an arithmetic expression string and return a Decimal.

    Parameters:
        expression (str): The arithmetic expression string to evaluate (e.g., "(100 - 20) / 4").

    Returns:
        Decimal: The exact computed result.

    Raises:
        UnsafeExpressionError: If the expression has invalid syntax, unauthorized nodes,
                               invalid input types, exceeds length or complexity limits,
                               or contains non-finite numbers.
        SafeDivisionByZeroError: If a division by zero occurs.
        SafeArithmeticError: If an arithmetic overflow, underflow, or calculation error occurs.
        SafeMathError: Base class for all safe math exceptions.

    Examples:
        >>> evaluate_expression("10 + 20")
        Decimal('30')
        >>> evaluate_expression("(100 * 0.20) + 15")
        Decimal('35.00')
        >>> evaluate_expression("10 / 0")
        Traceback (most recent call last):
            ...
        SafeDivisionByZeroError: Division by zero is not permitted.
    """
    if not isinstance(expression, str):
        raise UnsafeExpressionError(
            f"Expression must be a string, got {type(expression).__name__}."
        )

    # 1. Enforce length limit
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError(
            f"Expression length ({len(expression)}) exceeds maximum allowed limit of {MAX_EXPRESSION_LENGTH} characters."
        )

    cleaned_expr = expression.strip()
    if not cleaned_expr:
        raise UnsafeExpressionError("Expression cannot be empty.")

    # 2. Parse into AST
    try:
        parsed_ast = ast.parse(cleaned_expr, mode="eval")
    except (SyntaxError, ValueError) as e:
        raise UnsafeExpressionError(f"Syntax error in expression '{cleaned_expr}': {e}")

    # The body of an 'eval' mode AST is always an ast.Expression
    if not isinstance(parsed_ast, ast.Expression):
        raise UnsafeExpressionError("Invalid expression structure.")

    # 3. Enforce AST total node count limit
    total_nodes = sum(1 for _ in ast.walk(parsed_ast))
    if total_nodes > MAX_AST_NODES:
        raise UnsafeExpressionError(
            f"Expression complexity too high: {total_nodes} nodes exceeds limit of {MAX_AST_NODES}."
        )

    # 4. Enforce AST nesting depth limit
    _check_ast_depth(parsed_ast.body, current_depth=1)

    # 5. Evaluate and return Decimal
    return _eval_ast_node(parsed_ast.body)
