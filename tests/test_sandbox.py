from app.sandbox import analyze_python_code

def test_linter_finds_syntax_error():
    assert "syntax: FAIL" in analyze_python_code("def broken(:\n return 1\n")

def test_valid_syntax_passes():
    assert "syntax: PASS" in analyze_python_code("def add(a, b):\n    return a + b\n")
