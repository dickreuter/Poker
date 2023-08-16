import React from 'react';
import { Bar, BarChart, CartesianGrid, LabelList, Tooltip, XAxis, YAxis } from 'recharts';

interface LeagueTablePlotProps {
    data: Array<{ _id: string, 'Return per bb in 100 Hands': number, count: number }>;
}

const CustomTooltip = ({ active, payload }) => {
    if (active) {
        return (
            <div style={{ backgroundColor: 'white', padding: '5px', border: '1px solid #ccc' }}>
                <p>{`Strategy: ${payload[0].payload._id}`}</p>
                <p>{`Return: ${payload[0].value.toFixed(2)}`}</p>
                <p>{`Count: ${payload[0].payload.count}`}</p>
            </div>
        );
    }
    return null;
};

function transformData(data) {
    if (typeof data === 'string') {
        try {
            data = JSON.parse(data);
        } catch (err) {
            console.error('Error parsing the data string into JSON:', err);
            return []; // or throw an error
        }
    }
    return data
        .map(item => ({
            ...item,
            Total: parseInt(item.Total),
            count: parseInt(item.count, 10),
            'Return per bb in 100 Hands': parseFloat(item['Return per bb in 100 Hands'])
        }))
        .sort((a, b) => b['Return per bb in 100 Hands'] - a['Return per bb in 100 Hands']);  // Sort the data
}
// ... [Rest of the code]

const LeagueTablePlot: React.FC<LeagueTablePlotProps> = ({ data }) => {
    const transformedData = transformData(data);

    const counts = transformedData.map(d => d.count);
    const minCount = Math.min(...counts);
    const maxCount = Math.max(...counts);

    const normalize = (value, min, max) => (value - min) / (max - min);

    // Create the colors array just as before
    const colors = counts.map(count => {
        const normalizedValue = normalize(count, minCount, maxCount);
        const red = Math.round(136 + (normalizedValue * (255 - 136)));
        const green = 132;
        const blue = 216;
        return `rgb(${red}, ${green}, ${blue})`;
    });

    console.log(colors);  // Debugging line: Let's check if our colors array looks correct

    // Add the computed color to each data entry
    transformedData.forEach((item, index) => {
        item.color = colors[index];
    });

    console.log(transformedData);  // Debugging line: Check if each data entry now has a color property

    return (
        <BarChart width={1000} height={800} layout="vertical" data={transformedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis dataKey="_id" type="category" height={150} width={150} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="Return per bb in 100 Hands" fill="#8884d8">
                <LabelList dataKey="Return per bb in 100 Hands" position="right" formatter={value => value.toFixed(2)} />
            </Bar>
        </BarChart>
    );
};

export default LeagueTablePlot;
