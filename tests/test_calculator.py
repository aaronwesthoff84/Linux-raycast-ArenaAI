from raycast_linux.logic.calculator import CalcError, calculate, try_calculate


def test_basic_arithmetic():
    assert calculate("2+2") == "4"
    assert calculate("2+2*3") == "8"
    assert calculate("(2+2)*3") == "12"
    assert calculate("10-4-3") == "3"
    assert calculate("10/4") == "2.5"
    assert calculate("7%3") == "1"


def test_precedence_and_power():
    assert calculate("2^10") == "1024"
    assert calculate("2^3^2") == "512"  # right associative
    assert calculate("2*3+4") == "10"


def test_unary():
    assert calculate("-5+3") == "-2"
    assert calculate("5--3") == "8"
    assert calculate("-(2+3)") == "-5"
    assert calculate("+7") == "7"


def test_floats_and_scientific():
    assert calculate("1/3") == "0.3333333333"
    assert calculate("0.1+0.2") == "0.3"
    assert calculate("3e2+1") == "301"
    assert calculate("1.5e-2") == "0.015"


def test_functions_and_constants():
    assert calculate("sqrt(16)") == "4"
    assert calculate("sqrt 16") == "4"
    assert calculate("abs(-4)") == "4"
    assert calculate("2pi") == "6.2831853072"
    assert calculate("sin(0)") == "0"
    assert calculate("floor(3.9)") == "3"
    assert calculate("ceil(3.1)") == "4"


def test_implicit_multiplication():
    assert calculate("3(4+1)") == "15"
    assert calculate("2pi") == "6.2831853072"
    assert calculate("(1+1)(2+2)") == "8"


def test_errors():
    for bad in ("1/0", "1%0", "((2+3)", "2+*3", "foo(1)", ""):
        try:
            calculate(bad)
        except CalcError:
            pass
        else:
            raise AssertionError(f"{bad!r} should raise CalcError")


def test_try_calculate_gates():
    assert try_calculate("hello world") is None
    assert try_calculate("42") is None  # a bare number is not an expression
    assert try_calculate("abc") is None
    assert try_calculate("2+2") == "4"
    assert try_calculate("  2 + 2 = ") == "4"
