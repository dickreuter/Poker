import json
from weakref import proxy

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import gridspec
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


class BarPlotter2(FigureCanvas):
    def __init__(self, ui, initialize=False):
        self.ui = proxy(ui)
        if initialize:
            self.fig = Figure(dpi=50)
        else:
            self.fig = Figure()

        super(BarPlotter2, self).__init__(self.fig)
        try:
            self.ui.vLayout_bar.insertWidget(1, self)
        except:
            self.ui.vLayout2.insertWidget(1, self)
            if initialize:
                self.axes = self.fig.add_subplot(111)

    def drawfigure(self, gamelogger, strategy, last_stage='All', action_type='All', show_rounds=False,
                   my_computer_only=False):
        self.fig.clf()
        try:
            groups = ["gs", "rd", "fa", "ld"] if show_rounds else ["gs", "fa", "ld"]

            df = gamelogger.get_stacked_bar_data2('Template', str(strategy), 'stackedBar', last_stage=last_stage,
                                                  last_action=action_type, my_computer_only=my_computer_only)
            df = df[df['rd'].isin(['0', '1', '2'])]
            df = df.groupby(groups)["Total"].sum().unstack(fill_value=0)
            df = df.reindex(sorted(df.columns, reverse=True), axis=1)
            if show_rounds:
                df = df.sort_index(level=[2, 1], ascending=[False, True], axis=0)
            else:
                df = df.sort_index(level=[1], ascending=[False], axis=0)
        except json.decoder.JSONDecodeError:
            self.draw()
            return

        clusters = df.index.levels[0]
        inter_graph = 0
        maxi = np.max(np.sum(df, axis=1))
        total_width = len(df) + inter_graph * (len(clusters) - 1)

        gridspec.GridSpec(1, total_width)
        axes = []

        color_dict = {'Fold': 'red',
                      'Call': 'green',
                      'Bet half pot': 'b',
                      'Check': '#f2f2f2',
                      'Bet': 'c',
                      'Bet pot': '#330000',
                      'Check Deception': 'yellow',
                      'Bet Bluff': 'y'}

        ax_position = 0
        for cluster in ['PreFlop', 'Flop', 'Turn', 'River']:
            try:
                subset = df.loc[cluster]
            except KeyError:
                continue

            self.axes = subset.plot(kind="bar", stacked=True, width=0.8,
                                    color=[color_dict.get(x, 'brown') for x in subset.columns],
                                    ax=plt.subplot2grid((1, total_width), (0, ax_position),
                                                        fig=self.fig,
                                                        colspan=len(subset.index)))
            axes.append(self.axes)
            self.axes.set_title(cluster)
            self.axes.set_xlabel("")
            self.axes.set_xticklabels(self.axes.get_xticklabels(), rotation=35, ha='right', fontsize=9)
            self.axes.xaxis.set_tick_params(labelsize='small')

            self.axes.set_ylim(0, maxi + 1)
            self.axes.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax_position += len(subset.index) + inter_graph

        for i in range(1, len(clusters)):
            axes[i].set_yticklabels("")
            axes[i - 1].legend().set_visible(False)
        axes[0].set_ylabel("Payoff")

        legend = axes[-1].legend(loc='upper right', fontsize=9, framealpha=.3).get_frame()
        legend.set_linewidth(.5)
        legend.set_edgecolor("black")

        self.draw()
