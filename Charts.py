import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.spines import Spine
from matplotlib.projections.polar import PolarAxes
from matplotlib.projections import register_projection
from Xml_handler import *
from Log_manager import *

def radar_factory(num_vars, frame='circle'):
    """Create a radar chart with `num_vars` axes.

    This function creates a RadarAxes projection and registers it.

    Parameters
    ----------
    num_vars : int
        Number of variables for radar chart.
    frame : {'circle' | 'polygon'}
        Shape of frame surrounding axes.

    """
    # calculate evenly-spaced axis angles
    theta = 2 * np.pi * np.linspace(0, 1 - 1. / num_vars, num_vars)
    # rotate theta such that the first axis is at the top
    theta += np.pi / 2

    def draw_poly_patch(self):
        verts = unit_poly_verts(theta)
        return plt.Polygon(verts, closed=True, edgecolor='k')

    def draw_circle_patch(self):
        # unit circle centered on (0.5, 0.5)
        return plt.Circle((0.5, 0.5), 0.5)

    patch_dict = {'polygon': draw_poly_patch, 'circle': draw_circle_patch}
    if frame not in patch_dict:
        raise ValueError('unknown value for `frame`: %s' % frame)

    class RadarAxes(PolarAxes):

        name = 'radar'
        # use 1 line segment to connect specified points
        RESOLUTION = 1
        # define draw_frame method
        draw_patch = patch_dict[frame]

        def fill(self, *args, **kwargs):
            """Override fill so that line is closed by default"""
            closed = kwargs.pop('closed', True)
            return super(RadarAxes, self).fill(closed=closed, *args, **kwargs)

        def plot(self, *args, **kwargs):
            """Override plot so that line is closed by default"""
            lines = super(RadarAxes, self).plot(*args, **kwargs)
            for line in lines:
                self._close_line(line)

        def _close_line(self, line):
            x, y = line.get_data()
            if x[0] != x[-1]:
                x = np.concatenate((x, [x[0]]))
                y = np.concatenate((y, [y[0]]))
                line.set_data(x, y)

        def set_varlabels(self, labels):
            self.set_thetagrids(theta * 180 / np.pi, labels)

        def _gen_axes_patch(self):
            return self.draw_patch()

        def _gen_axes_spines(self):
            if frame == 'circle':
                return PolarAxes._gen_axes_spines(self)
            # The following is a hack to get the spines (i.e. the axes frame)
            # to draw correctly for a polygon frame.

            # spine_type must be 'left', 'right', 'top', 'bottom', or `circle`.
            spine_type = 'circle'
            verts = unit_poly_verts(theta)
            # close off polygon by repeating first vertex
            verts.append(verts[0])
            path = Path(verts)

            spine = Spine(self, spine_type, path)
            spine.set_transform(self.transAxes)
            return {'polar': spine}

    register_projection(RadarAxes)
    return theta

def unit_poly_verts(theta):
    """Return vertices of polygon for subplot axes.

    This polygon is circumscribed by a unit circle centered at (0.5, 0.5)
    """
    x0, y0, r = [0.5] * 3
    verts = [(r * np.cos(t) + x0, r * np.sin(t) + y0) for t in theta]
    return verts

def show_spider(p):
    L = Logging('log')
    data = L.get_stacked_bar_data('Template', p, 'spider')

    N = 12
    theta = radar_factory(N, frame='polygon')

    spoke_labels = data.pop('column names')

    fig = plt.figure(figsize=(7, 7))
    fig.subplots_adjust(wspace=0.25, hspace=0.20, top=0.85, bottom=0.05)

    colors = ['r', 'g', 'b', 'm', 'y']
    # Plot the four cases from the example data on separate axes
    for n, title in enumerate(data.keys()):
        ax = fig.add_subplot(1, 1, n + 1, projection='radar')
        # plt.rgrids([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        ax.set_title(title, weight='bold', size='medium', position=(0.5, 1.1),
                     horizontalalignment='center', verticalalignment='center')
        for d, color in zip(data[title], colors):
            ax.plot(theta, d, color=color)
            ax.fill(theta, d, facecolor=color, alpha=0.25)
        ax.set_varlabels(spoke_labels)

    # add legend relative to top-left plot
    plt.subplot(1, 1, 1)
    labels = ('Losers', 'Winners')
    legend = plt.legend(labels, loc=(0.9, .95), labelspacing=0.1)
    plt.setp(legend.get_texts(), fontsize='small')

    plt.figtext(0.5, 0.965, 'Winner vs Losers',
                ha='center', color='black', weight='bold', size='large')
    plt.show()

def setup_backend(backend='TkAgg'):
    import sys
    del sys.modules['matplotlib.backends']
    del sys.modules['matplotlib.pyplot']
    import matplotlib as mpl
    mpl.use(backend)  # do this before importing pyplot
    import matplotlib.pyplot as plt
    return plt

def show_histogram(template, gameStage, decision):
    L = Logging('log')
    data = L.get_histrogram_data(template, p_name, gameStage, decision)
    wins = data[0]
    losses = data[1]
    bins = np.linspace(0, 1, 25)

    plt.hist(wins, bins, alpha=0.5, label='wins', color='g')
    plt.hist(losses, bins, alpha=0.5, label='losses', color='r')
    plt.legend(loc='upper right')
    plt.show()

def show_stacked_bars(p_name):
    L = Logging('log')
    data = L.get_stacked_bar_data('Template', p_name, 'stackedBar')
    N = 11
    Bluff = data[0]
    BP = data[1]
    BHP = data[2]
    Bet = data[3]
    Call = data[4]
    Check = data[5]
    Fold = data[6]
    ind = np.arange(N)  # the x locations for the groups
    width = 1  # the width of the bars: can also be len(x) sequence

    p0 = plt.bar(ind, Bluff, width, color='y')
    p1 = plt.bar(ind, BP, width, color='k', bottom=Bluff)
    p2 = plt.bar(ind, BHP, width, color='b', bottom=[sum(x) for x in zip(Bluff, BP)])
    p3 = plt.bar(ind, Bet, width, color='c', bottom=[sum(x) for x in zip(Bluff, BP, BHP)])
    p4 = plt.bar(ind, Call, width, color='g', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet)])
    p5 = plt.bar(ind, Check, width, color='w', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call)])
    p6 = plt.bar(ind, Fold, width, color='r', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call, Check)])

    plt.ylabel('Profitability')
    plt.title('FinalFundsChange ABS')
    plt.xticks(ind + width / 2., ('PF Win', 'Loss', '', 'F Win', 'Loss', '', 'T Win', 'Loss', '', 'R Win', 'Loss'))
    # plt.yticks(np.arange(0,10,0.5))
    plt.legend((p0[0], p1[0], p2[0], p3[0], p4[0], p5[0], p6[0]),
               ('Bluff', 'BetPot', 'BetHfPot', 'Bet/Bet+', 'Call', 'Check', 'Fold'))

    i = 0
    for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(p0.patches, p1.patches, p2.patches, p3.patches,
                                                               p4.patches, p5.patches, p6.patches):
        g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
        h = g[i]
        i += 1
        rect0.set_height(h[0])
        rect1.set_y(h[0])
        rect1.set_height(h[1])
        rect2.set_y(h[0] + h[1])
        rect2.set_height(h[2])
        rect3.set_y(h[0] + h[1] + h[2])
        rect3.set_height(h[3])
        rect4.set_y(h[0] + h[1] + h[2] + h[3])
        rect4.set_height(h[4])
        rect5.set_y(h[0] + h[1] + h[2] + h[3] + h[4])
        rect5.set_height(h[5])
        rect6.set_y(h[0] + h[1] + h[2] + h[3] + h[4] + h[5])
        rect6.set_height(h[6])

    plt.show()

if __name__ == '__main__':
    p = XMLHandler('strategies.xml')
    p.read_XML()
    template = 'Template'
    p_name = p.current_strategy.text
    p_name = 'PPStrategy3002d'
    # template='decision'
    # p_name='Call'

    # showSpider(p_name)
    show_stacked_bars(p_name)
    # showHistogram(template,'PreFlop','Call')
