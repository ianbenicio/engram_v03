from engram.core.rate_limit import RateLimiter

def test_allows_under_limit():
    rl = RateLimiter(max_calls=3, window_seconds=60)
    assert rl.allow("vault.save")
    assert rl.allow("vault.save")
    assert rl.allow("vault.save")

def test_blocks_over_limit():
    rl = RateLimiter(max_calls=2, window_seconds=60)
    rl.allow("t"); rl.allow("t")
    assert rl.allow("t") is False

def test_per_tool_isolation():
    rl = RateLimiter(max_calls=1, window_seconds=60)
    assert rl.allow("a")
    assert rl.allow("b")
    assert rl.allow("a") is False

def test_window_expiry(monkeypatch):
    import engram.core.rate_limit as m
    t = [1000.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: t[0])
    rl = RateLimiter(max_calls=1, window_seconds=10)
    assert rl.allow("x")
    assert rl.allow("x") is False
    t[0] += 11
    assert rl.allow("x")
