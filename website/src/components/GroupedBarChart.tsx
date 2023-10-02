import { Component } from 'react';
import {
    Bar,
    BarChart,
    CartesianGrid,
    Legend,
    Tooltip,
    XAxis, YAxis
} from 'recharts';

class GroupedStackedBarChart extends Component {
    constructor(props) {
        super(props);
        this.state = {
            cursorData: null,
        };
        this.handleMouseMove = this.handleMouseMove.bind(this);
    }

    handleMouseMove(e) {
        if (e && e.activePayload) {
            const hoveredData = e.activePayload[0].payload;

            if (hoveredData) {
                let cursorData = null;

                for (const key in hoveredData) {
                    if (hoveredData[key] === e.activePayload[0].value) {
                        cursorData = { name: key, value: hoveredData[key] };
                        break;
                    }
                }

                this.setState({ cursorData });
            }
        } else {
            this.setState({ cursorData: null });
        }
    }

    render() {
        const { data } = this.props;
        const actions = ["Fold", "Check Deception", "Check", "Call", "Bet half pot", "Bet Bluff", "Bet pot"];

        // Order the data based on the groups
        const stagesOrder = ["PreFlop", "Flop", "Turn", "River"];
        data.sort((a, b) => {
            if (a.gs !== b.gs) {
                return stagesOrder.indexOf(a.gs) - stagesOrder.indexOf(b.gs);
            }
            return a.fa === 'Won' ? -1 : 1;
        });



        return (
            <>
                <div className="h4">
                    Wins and Losses per stage for given action type
                </div>
                <BarChart
                    width={800}
                    height={400}
                    data={data}
                    layout="horizontal"
                    barCategoryGap={0}
                    barGap={10}
                    onMouseMove={this.handleMouseMove}
                >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="gs" tick={<CustomizedAxisTick data={data} />} height={70} interval={0} />
                    <YAxis />
                    <Legend />
                    <Tooltip />


                    {actions.map(action => (
                        <Bar
                            key={action}
                            dataKey={action}
                            stackId="a"
                            fill={getFillColor(action)}
                            cursor={{ fill: 'transparent' }}
                        />
                    ))}
                </BarChart>
            </>
        );
    }
}

function getFillColor(action) {
    const colors =
    {
        'Fold': 'red',
        'Call': 'green',
        'Bet half pot': 'blue',
        'Check': 'lightgrey',
        'Bet': 'lightblue',
        'Bet pot': 'black',
        'Check Deception': 'darkgrey',
        'Bet Bluff': 'orange'
    };
    return colors[action];
}

const CustomizedAxisTick = (props) => {
    const { x, y, index, data } = props;

    const currentData = data[index];
    const label = currentData.fa;
    const isEvenTick = index % 2 === 0;

    return (
        <g transform={`translate(${x},${y})`}>
            <text x={50} y={10} dy={16} textAnchor="middle" fill="#666">
                {isEvenTick ? (
                    currentData.gs
                ) : null}
            </text>
            <text x={0} y={20} dy={-10} textAnchor="middle" fill="#666">
                {label}
            </text>
        </g>
    );
};

const CustomTooltip = ({ active, cursorData }) => {
    if (active && cursorData) {
        return (
            <div style={{ backgroundColor: 'white', padding: '10px', border: '1px solid #ccc' }}>
                <p className="label">{`${cursorData.name}`}</p>
                <p className="desc">{`Value : ${cursorData.value}`}</p>
            </div>
        );
    }

    return null;
};


export default GroupedStackedBarChart;