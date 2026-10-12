from adintel.harness.admission import RedisRateLimiter, make_limiter, run_limiter
from adintel.llm.semantic_cache import RedisSemanticCache, get_semantic_cache


def test_limiter_window_is_shared_between_processes(fake_redis):
    a = RedisRateLimiter("runs", limit=3)  # "API process"
    b = RedisRateLimiter("runs", limit=3)  # "scheduler process"
    assert a.allow("t1") and b.allow("t1") and a.allow("t1")
    assert not b.allow("t1")  # the 4th hit is refused whichever process makes it
    assert a.allow("t2")  # per-tenant keys


def test_factory_picks_redis_in_shared_mode(fake_redis):
    assert isinstance(make_limiter("x", 1), RedisRateLimiter)
    assert isinstance(run_limiter(), RedisRateLimiter)
    assert isinstance(get_semantic_cache(), RedisSemanticCache)


def test_redis_semantic_cache_is_scoped_by_tenant_and_brand(fake_redis):
    c1, c2 = RedisSemanticCache(), RedisSemanticCache()
    c1.put("t1", "b1", "What was spend last week?", {"answer": "$10"})
    assert c2.get("t1", "b1", "what was spend last week")["answer"] == "$10"
    assert c2.get("t1", "b2", "What was spend last week?") is None
    assert c2.get("t2", "b1", "What was spend last week?") is None
    assert fake_redis.ttl("adintel:semcache:t1:b1") > 0


def test_redis_outage_degrades_safely(fake_redis, monkeypatch):
    class Broken:
        def pipeline(self):
            raise ConnectionError("down")

        def lrange(self, *a):
            raise ConnectionError("down")

    from adintel.core import redis_client

    monkeypatch.setattr(redis_client, "_client", Broken())
    assert RedisRateLimiter("x", 1).allow("t")  # fail open: capacity control, not safety
    assert RedisSemanticCache().get("t", "b", "q") is None  # a cache outage is a miss
