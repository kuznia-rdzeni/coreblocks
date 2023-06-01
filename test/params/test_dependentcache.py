import unittest

from coreblocks.params.genparams import DependentCache


class TestDependentCache(unittest.TestCase):
    class WithCache(DependentCache):
        def __init__(self, x=1):
            super().__init__()
            self.x = x

    class CachedObject:
        count = 0

        def __init__(self, wc):
            self.__class__.count += 1
            self.x = wc.x

    class CachedObjectWithArgs:
        def __init__(self, wc, *, f, s):
            self.wc = wc
            self.f = f
            self.s = s

    class CachedObjectKwArgsOnly:
        def __init__(self, *, f, s):
            self.f = f
            self.s = s

    def test_cache(self):
        count = TestDependentCache.CachedObject.count
        wc = TestDependentCache.WithCache(1)
        obj = wc.get(TestDependentCache.CachedObject)
        self.assertEqual(obj.x, wc.x)
        obj2 = wc.get(TestDependentCache.CachedObject)
        self.assertEqual(TestDependentCache.CachedObject.count, count + 1)
        self.assertIs(obj, obj2)

    def test_cache_kwargs(self):
        wc = TestDependentCache.WithCache()
        obj = wc.get(TestDependentCache.CachedObjectWithArgs, f=1, s=2)
        self.assertEqual(obj.f, 1)
        self.assertEqual(obj.s, 2)

    def test_cache_kwargs_only(self):
        wc = TestDependentCache.WithCache()
        obj = wc.get(TestDependentCache.CachedObjectKwArgsOnly, f=1, s=2)
        self.assertEqual(obj.f, 1)
        self.assertEqual(obj.s, 2)
