import unittest

from coreblocks.genparams import DependentCache


class TestDependentCache(unittest.TestCase):
    class WithCache(DependentCache):
        def __init__(self, x):
            super().__init__()
            self.x = x

    class CachedObject:
        count = 0

        def __init__(self, wc):
            self.__class__.count += 1
            self.x = wc.x

    def test_cache(self):
        count = TestDependentCache.CachedObject.count
        wc = TestDependentCache.WithCache(1)
        obj = wc.get(TestDependentCache.CachedObject)
        self.assertEqual(obj.x, wc.x)
        obj2 = wc.get(TestDependentCache.CachedObject)
        self.assertEqual(TestDependentCache.CachedObject.count, count + 1)
        self.assertIs(obj, obj2)
