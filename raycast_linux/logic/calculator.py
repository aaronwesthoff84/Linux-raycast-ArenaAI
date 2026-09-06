"""Safe math expression evaluator — no ``eval``, pure shunting yard.

Supported: ``+ - * / % ^`` (``%`` = modulo), parentheses, unary minus,
implicit multiplication (``2pi``, ``3(4+1)``), constants ``pi e tau phi``
and functions ``sqrt sin cos tan asin acos atan log log2 ln abs floor
ceil round exp cbrt``.
"""
from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(
    r"""
    (?P<num>\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[-+*/%^(),])
  | (?P<ws>\s+)
    """,
    re.X,
)

_SAFE_INPUT = re.compile(r"^[-+*/%^().,a-zA-Z0-9 eE]*$")

_HAS_MATH = re.compile(
    r"[-+*/%^]"
    r"|(?<![A-Za-z])(?:sqrt|cbrt|sin|cos|tan|asin|acos|atan|log10|log2|log"
    r"|ln|abs|floor|ceil|round|exp|pi|tau|phi|e)(?![A-Za-z0-9])"
)


class CalcError(ValueError):
    """Raised for any malformed or non-computable expression."""


FUNCS: dict[str, callable] = {
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log10,
    "log10": math.log10,
    "log2": math.log2,
    "ln": math.log,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": lambda x: float(round(x)),
    "exp": math.exp,
}

CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "phi": (1.0 + 5.0 ** 0.5) / 2.0,
}

_PREC = {"u-": 5, "^": 4, "*": 3, "/": 3, "%": 3, "+": 2, "-": 2}
_RIGHT = {"u-", "^"}


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise CalcError(f"Unexpected character {text[pos]!r} at position {pos}")
        pos = m.end()
        kind = m.lastgroup or ""
        if kind == "ws":
            continue
        tokens.append((kind, m.group(kind)))
    return tokens


def _insert_implicit_mul(tokens: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for tok in tokens:
        if out:
            pk, pv = out[-1]
            ck, cv = tok
            # A function name is NOT a value: sqrt(16) must not become sqrt*(16).
            prev_value = pk == "num" or (pk == "name" and pv in CONSTS) or (pk == "op" and pv == ")")
            cur_value = ck == "num" or ck == "name" or (ck == "op" and cv == "(")
            if prev_value and cur_value:
                out.append(("op", "*"))
        out.append(tok)
    return out


def _mark_unary(tokens: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    prev_value = False
    for k, v in tokens:
        if k == "op" and v in "+-" and not prev_value:
            if v == "-":
                out.append(("op", "u-"))
            continue  # unary plus is a no-op
        out.append((k, v))
        prev_value = k == "num" or k == "name" or (k == "op" and v == ")")
    return out


def _to_rpn(tokens: list[tuple[str, str]]) -> list[tuple[str, float | str]]:
    out: list[tuple[str, float | str]] = []
    ops: list[tuple[str, str]] = []
    for k, v in tokens:
        if k == "num":
            out.append(("num", float(v)))
        elif k == "name":
            if v in CONSTS:
                out.append(("num", CONSTS[v]))
            elif v in FUNCS:
                ops.append(("func", v))
            else:
                raise CalcError(f"Unknown name: {v}")
        else:
            if v == "(":
                ops.append(("op", v))
            elif v == ")":
                while ops and ops[-1] != ("op", "("):
                    out.append(ops.pop())
                if not ops:
                    raise CalcError("Mismatched parentheses")
                ops.pop()
                if ops and ops[-1][0] == "func":
                    out.append(ops.pop())
            else:
                while ops:
                    top = ops[-1]
                    if top[0] == "func":
                        out.append(ops.pop())
                        continue
                    if top == ("op", "("):
                        break
                    tv = top[1]
                    if _PREC[tv] > _PREC[v] or (_PREC[tv] == _PREC[v] and v not in _RIGHT):
                        out.append(ops.pop())
                    else:
                        break
                ops.append(("op", v))
    while ops:
        top = ops.pop()
        if top == ("op", "("):
            raise CalcError("Mismatched parentheses")
        out.append(top)
    return out


def _eval_rpn(rpn: list[tuple[str, float | str]]) -> float:
    stack: list[float] = []
    for kind, val in rpn:
        if kind == "num":
            stack.append(val)
        elif kind == "func":
            if not stack:
                raise CalcError("Bad function call")
            a = stack.pop()
            try:
                stack.append(FUNCS[val](a))
            except (ValueError, OverflowError):
                raise CalcError("Function argument out of domain") from None
        else:
            if val == "u-":
                if not stack:
                    raise CalcError("Bad expression")
                stack.append(-stack.pop())
                continue
            if len(stack) < 2:
                raise CalcError("Bad expression")
            b, a = stack.pop(), stack.pop()
            if val == "+":
                r = a + b
            elif val == "-":
                r = a - b
            elif val == "*":
                r = a * b
            elif val == "/":
                if b == 0:
                    raise CalcError("Division by zero")
                r = a / b
            elif val == "%":
                if b == 0:
                    raise CalcError("Division by zero")
                r = a % b
            elif val == "^":
                if abs(a) > 1e6 and abs(b) > 1e6:
                    raise CalcError("Result too large")
                r = a ** b
            else:  # pragma: no cover
                raise CalcError(f"Unknown operator {val}")
            stack.append(r)
    if len(stack) != 1:
        raise CalcError("Bad expression")
    return stack[0]


def _fmt(x: float) -> str:
    if math.isnan(x) or math.isinf(x):
        raise CalcError("Result is not a finite number")
    if x != 0 and (abs(x) >= 1e16 or abs(x) < 1e-9):
        return f"{x:.6e}"
    r = round(x, 10)
    if r == int(r) and abs(r) < 1e16:
        return str(int(r))
    return f"{r:.10f}".rstrip("0").rstrip(".")


def calculate(text: str) -> str:
    """Evaluate ``text`` and return a formatted result string.

    Raises :class:`CalcError` when the expression is invalid.
    """
    t = text.strip().rstrip("=").strip()
    if not t or len(t) > 200:
        raise CalcError("Empty or too long expression")
    if not _SAFE_INPUT.match(t):
        raise CalcError("Unsupported characters")
    if not _HAS_MATH.search(t):
        raise CalcError("Not a math expression")
    tokens = _tokenize(t)
    if not tokens:
        raise CalcError("Empty expression")
    tokens = _insert_implicit_mul(tokens)
    tokens = _mark_unary(tokens)
    return _fmt(_eval_rpn(_to_rpn(tokens)))


def try_calculate(text: str) -> str | None:
    """Like :func:`calculate` but returns ``None`` instead of raising."""
    try:
        return calculate(text)
    except CalcError:
        return None
