"""
Calculator Plugin
Safe mathematical expression evaluation with support for common functions
"""
import ast
import math
import operator
import re
import time
from typing import Any

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class CalculatorPlugin(IPlugin):
    """
    Safe calculator that evaluates mathematical expressions.

    Features:
    - Safe expression evaluation (no code execution)
    - Support for basic operators (+, -, *, /, **, %, //)
    - Support for common functions (sin, cos, tan, sqrt, log, abs, etc.)
    - Support for constants (pi, e)
    - Protection against malicious input
    """

    # Allowed operators
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # Allowed functions
    FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        # Math functions
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sinh": math.sinh,
        "cosh": math.cosh,
        "tanh": math.tanh,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "pow": math.pow,
        "ceil": math.ceil,
        "floor": math.floor,
        "degrees": math.degrees,
        "radians": math.radians,
    }

    # Allowed constants
    CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf,
    }

    def __init__(self) -> None:
        """Initialize calculator plugin."""
        metadata = PluginMetadata(
            name="calculator",
            version="1.0.0",
            description="Safe mathematical expression evaluator",
            author="Ironclaw Team",
            dependencies=[],
            max_execution_time_seconds=5,
            max_memory_mb=128,
            max_cpu_percent=20.0,
            requires_network=False,
            enabled=True,
            tags=["math", "calculator", "utility"],
        )
        super().__init__(metadata)

    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Evaluate mathematical expression.

        Args:
            expression: Mathematical expression to evaluate (required)
            precision: Number of decimal places (default: 10)

        Returns:
            PluginResult with calculated result
        """
        start_time = time.time()

        try:
            # Extract parameters
            expression = kwargs.get("expression", "").strip()
            precision = int(kwargs.get("precision", 10))

            if not expression:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="Expression parameter is required",
                )

            # Parse and evaluate expression
            result = self._evaluate_expression(expression)

            # Round result if needed
            if isinstance(result, float):
                result = round(result, precision)

            execution_time_ms = int((time.time() - start_time) * 1000)

            return PluginResult(
                status=PluginStatus.SUCCESS,
                data={
                    "expression": expression,
                    "result": result,
                    "result_type": type(result).__name__,
                },
                execution_time_ms=execution_time_ms,
            )

        except SyntaxError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Syntax error in expression: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

        except ValueError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Invalid value in expression: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

        except ZeroDivisionError:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error="Division by zero",
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Calculation failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate expression.

        Args:
            expression: Expression to validate

        Returns:
            True if valid, False otherwise
        """
        expression = kwargs.get("expression", "").strip()

        if not expression:
            return False

        if len(expression) > 1000:
            return False

        # Check for dangerous patterns
        dangerous_patterns = [
            r"__",  # Double underscore (dunder methods)
            r"import",
            r"exec",
            r"eval",
            r"compile",
            r"open",
            r"file",
            r"input",
            r"raw_input",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, expression, re.IGNORECASE):
                return False

        # Try to parse expression
        try:
            ast.parse(expression, mode="eval")
            return True
        except SyntaxError:
            return False

    def _evaluate_expression(self, expression: str) -> float | int | bool:
        """
        Safely evaluate mathematical expression.

        Args:
            expression: Expression to evaluate

        Returns:
            Evaluated result

        Raises:
            ValueError: If expression contains unsafe operations
            SyntaxError: If expression has syntax errors
        """
        # Parse expression into AST
        tree = ast.parse(expression, mode="eval")

        # Evaluate AST
        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> Any:
        """
        Recursively evaluate AST node.

        Args:
            node: AST node to evaluate

        Returns:
            Evaluated result

        Raises:
            ValueError: If node contains unsafe operations
        """
        # Numbers
        if isinstance(node, ast.Constant):
            return node.value

        # Backward compatibility for Python < 3.8
        if isinstance(node, ast.Num):
            return node.n

        # Variables/Constants
        if isinstance(node, ast.Name):
            if node.id in self.CONSTANTS:
                return self.CONSTANTS[node.id]
            else:
                raise ValueError(f"Undefined constant: {node.id}")

        # Binary operations
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op = type(node.op)

            if op not in self.OPERATORS:
                raise ValueError(f"Unsupported operator: {op.__name__}")

            return self.OPERATORS[op](left, right)

        # Unary operations
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op = type(node.op)

            if op not in self.OPERATORS:
                raise ValueError(f"Unsupported unary operator: {op.__name__}")

            return self.OPERATORS[op](operand)

        # Function calls
        if isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None

            if func_name not in self.FUNCTIONS:
                raise ValueError(f"Unsupported function: {func_name}")

            func = self.FUNCTIONS[func_name]
            args = [self._eval_node(arg) for arg in node.args]

            return func(*args)

        # Comparison operations
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                
                if isinstance(op, ast.Lt):
                    result = left < right
                elif isinstance(op, ast.LtE):
                    result = left <= right
                elif isinstance(op, ast.Gt):
                    result = left > right
                elif isinstance(op, ast.GtE):
                    result = left >= right
                elif isinstance(op, ast.Eq):
                    result = left == right
                elif isinstance(op, ast.NotEq):
                    result = left != right
                else:
                    raise ValueError(f"Unsupported comparison: {type(op).__name__}")
                
                if not result:
                    return False
                    
                left = right
            
            return True

        # Lists/tuples (for functions like min, max, sum)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._eval_node(el) for el in node.elts]

        # Unsupported node type
        raise ValueError(f"Unsupported expression: {type(node).__name__}")

    async def cleanup(self) -> None:
        """No cleanup needed for calculator."""
        pass
