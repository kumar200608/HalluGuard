"""Calculation Validator.

Routes numeric claims to a deterministic Python evaluator.
Never trusts the LLM for arithmetic.
"""
from __future__ import annotations

import ast
import logging
import math
import operator
import re
from typing import Optional

from app.models.schemas import Claim

logger = logging.getLogger(__name__)

# Safe math operators
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_SAFE_NAMES = {
    "pi": math.pi,
    "e": math.e,
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}


class _SafeEval(ast.NodeVisitor):
    """Evaluate a math AST with no access to builtins or imports."""

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op)}")
        return op(left, right)

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op)}")
        return op(operand)

    def visit_Num(self, node):  # Python 3.7 compat
        return node.n

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")

    def visit_Name(self, node):
        if node.id in _SAFE_NAMES:
            return _SAFE_NAMES[node.id]
        raise ValueError(f"Unknown name: {node.id!r}")

    def visit_Call(self, node):
        func = self.visit(node.func)
        args = [self.visit(a) for a in node.args]
        return func(*args)

    def generic_visit(self, node):
        raise ValueError(f"Unsupported node: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    """Evaluate a pure mathematical expression safely. Raises on failure."""
    tree = ast.parse(expression.strip(), mode="eval")
    return _SafeEval().visit(tree)


# Patterns to extract arithmetic expressions from claim text
# Matches: LHS = RHS where LHS may contain digits, operators, %, ×, ÷, and words like "of"
_CALC_PATTERN = re.compile(
    r"([\d.,\s\+\-\*/\^\(\)%×÷xX]+(?:\s+of\s+[\d.,\s\+\-\*/\^\(\)%×÷xX]+)?)\s*[=≈]\s*([\d.,]+)",
    re.UNICODE,
)


def _normalize_expr(expr: str) -> str:
    # Replace word "of" used in percentage expressions: "20% of 500" → "20/100 * 500"
    # Handle "N% of M" specially
    pct_of = re.compile(r"([\d.]+)\s*%\s*of\s*([\d.]+)", re.IGNORECASE)
    expr = pct_of.sub(lambda m: f"({m.group(1)}/100*{m.group(2)})", expr)
    # Clean remaining
    expr = expr.replace(",", "").replace("^", "**")
    # Replace bare % that didn't get caught above
    expr = re.sub(r"([\d.]+)%", r"(\1/100)", expr)
    expr = expr.replace("×", "*").replace("✕", "*").replace("÷", "/")
    # Remove leftover "of" (shouldn't remain after pct_of sub, but safety)
    expr = expr.replace(" of ", "*")
    return expr.strip()


class CalculationValidator:
    """Extract and verify numeric calculations within a claim."""

    def validate(self, claim: Claim) -> tuple[Optional[bool], str]:
        """
        Returns (is_correct, explanation).
        is_correct=None means no calculable expression found.
        """
        text = claim.text

        # Look for "X op Y = Z" style expressions
        match = _CALC_PATTERN.search(text)
        if not match:
            return None, "No calculable expression detected."

        expr_raw = match.group(1)
        stated_result_raw = match.group(2)

        try:
            expr = _normalize_expr(expr_raw)
            stated_result = float(stated_result_raw.replace(",", ""))
            actual_result = safe_eval(expr)
        except Exception as exc:
            return None, f"Could not evaluate expression: {exc}"

        # Allow for floating point tolerance
        tolerance = max(abs(stated_result) * 1e-6, 1e-9)
        if abs(actual_result - stated_result) <= tolerance:
            return True, f"Calculation verified: {expr} = {actual_result}"
        else:
            return False, (
                f"Calculation error: stated {stated_result}, "
                f"actual {actual_result:.6g} (expression: {expr})"
            )


calculation_validator = CalculationValidator()
