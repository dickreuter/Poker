import virtualbox
vbox = virtualbox.VirtualBox()
print("VM(s):\n + %s" % "\n + ".join([vm.name for vm in vbox.machines]))
session = virtualbox.Session()
