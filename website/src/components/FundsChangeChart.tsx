import React, { Component } from 'react';
import {
    BarChart, Bar,
    CartesianGrid,
    Legend,
    Tooltip,
    XAxis, YAxis
} from 'recharts';
// ... (Rest of the imports)

class FundsChangeLineChart extends Component {
    constructor(props) {
        super(props);
        this.state = {
            cursorData: null,
        };
        this.handleMouseMove = this.handleMouseMove.bind(this);
    }

    handleMouseMove(e) {
        if (e && e.activePayload && e.activePayload[0]) {
            const hoveredData = e.activePayload[0].payload;
            if (hoveredData) {
                const cursorData = {
                    name: e.activePayload[0].name,
                    value: Number(e.activePayload[0].value).toFixed(2) // Format to 2 decimal places
                };
                this.setState({ cursorData });
            }
        } else {
            this.setState({ cursorData: null });
        }
    }

    render() {
        const { data } = this.props;

        const formattedData = data.map((value, index) => ({
            date: index,
            value: Number(value).toFixed(2) // Format to 2 decimal places
        }));

        return (
            <>
                <div className="h4">
                    Payoff for each played hand
                </div>
                <BarChart
                    width={800}
                    height={200}
                    data={formattedData}
                    onMouseMove={this.handleMouseMove}
                >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Legend />
                    <Tooltip content={<CustomTooltip cursorData={this.state.cursorData} />} />
                    <Bar dataKey="value" name="Hands Payoff" fill="#8884d8" />
                </BarChart>
            </>
        );
    }
}

const CustomTooltip = ({ active, cursorData }) => {
    if (active && cursorData) {
        return (
            <div style={{ backgroundColor: 'white', padding: '10px', border: '1px solid #ccc' }}>
                <p className="label">{`${cursorData.name}`}</p>
                <p className="desc">{`${cursorData.value}`}</p>
            </div>
        );
    }

    return null;
};

export default FundsChangeLineChart;
