from engram.hooks.pre_tool_use import compute_flag


def test_flag_normal_under_35():
    assert compute_flag(0, 1000, 200_000)["threshold"] == "normal"


def test_flag_warning_between_35_50():
    assert compute_flag(72_000, 0, 200_000)["threshold"] == "warning"


def test_flag_critical_over_50():
    assert compute_flag(100_001, 0, 200_000)["threshold"] == "critical"
