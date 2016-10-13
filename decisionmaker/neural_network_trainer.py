import neurolab as nl
import numpy as np

# Create train samples
x = np.linspace(-7, 7, 20)
y1 = np.sin(x) * 0.5
y2 = np.cos(x) * 0.5

size = len(x)

inp = x.reshape(size,1)
tar1 = y1.reshape(size,1)
tar2 = y2.reshape(size,1)
tar=np.concatenate((tar1,tar2),1)

# Create network with 2 layers and random initialized
net = nl.net.newff([[-7, 7]],[5, 2])

# Train network
error = net.train(inp, tar, epochs=5000, show=100, goal=0.02)

# Simulate network
out = net.sim(inp)

# Plot result
import pylab as pl
pl.subplot(211)
pl.plot(error)
pl.xlabel('Epoch number')
pl.ylabel('error (default SSE)')

x2 = np.linspace(-6.0,6.0,150)
y2 = net.sim(x2.reshape(x2.size,1))

# y3 = out.reshape(size)
#
# pl.subplot(212)
# pl.plot(x2, y2, '-',x , y, '.', x, y3, 'p')
# pl.legend(['train target', 'net output'])
pl.show()
