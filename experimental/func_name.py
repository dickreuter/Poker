import inspect
def somefunc():
    print (inspect.stack()[0][3])

somefunc()