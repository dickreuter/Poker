import multiprocessing as mp


class Singleton(type):
    def __init__(cls, name, bases, dict):
        super(Singleton, cls).__init__(name, bases, dict)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance


def foo(index):
    pass


class PoolManager(metaclass=Singleton):
    def __init__(self):
        self.pool = mp.Pool(4)

    def get(self):
        return self.pool

    def init_pool(self):
        self.pool.map(foo, range(100))

    def shutdown(self):
        self.pool.close()
        self.pool.join()
