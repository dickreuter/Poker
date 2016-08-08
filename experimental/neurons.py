"""
Example of use LVQ network
==========================

"""
import numpy as np
import neurolab as nl

# Create train samples
input = np.array([[+3, 0], [-2, 1], [-2, -1], [2, 2], [0, 1], [0, -1], [0, -2],
                  [2, 1], [2, -1], [3, 0]])
target = np.array([[1, 0], [1, 0], [0, 1], [0, 1], [0, 1], [0, 1], [0, 1],
                   [1, 0], [1, 0], [1, 0]])

from log_manager import *

p_name = 'Template'
p_value = ''
gameStage = 'PreFlop'
decision = 'Call'

# pivot_by_template()
LogFilename = 'log'
L = Logging(LogFilename)
input, target = L.get_neural_training_data(p_name, p_value, gameStage, decision)

# Create network with 2 layers:4 neurons in input layer(Competitive)
# and 2 neurons in output layer(liner)
net = nl.net.newlvq(nl.tool.minmax(input), 32, [.6, .4])
# Train network
error = net.train(input, target, epochs=1000, goal=-1)

# Plot result
import pylab as pl

xx, yy = np.meshgrid(np.arange(0, 1, 0.01), np.arange(0, 2, 0.01))
xx.shape = xx.size, 1
yy.shape = yy.size, 1
i = np.concatenate((xx, yy), axis=1)
o = net.sim(i)
grid1 = i[o[:, 0] > 0]
grid2 = i[o[:, 1] > 0]

class1 = input[target[:, 0] > 0]
class2 = input[target[:, 1] > 0]

pl.plot(class1[:, 0], class1[:, 1], 'bo', class2[:, 0], class2[:, 1], 'go')
pl.plot(grid1[:, 0], grid1[:, 1], 'b.', grid2[:, 0], grid2[:, 1], 'gx')
pl.axis([0, 1, 0, 1])
pl.xlabel('Input[:, 0]')
pl.ylabel('Input[:, 1]')
pl.legend(['class 1', 'class 2', 'detected class 1', 'detected class 2'])
pl.show()
