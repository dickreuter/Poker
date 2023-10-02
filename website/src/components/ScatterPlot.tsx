import React from 'react';
import { VictoryChart, VictoryScatter, VictoryTooltip, VictoryAxis } from 'victory';

interface RawData {
    wins: string;
    losses: string;
}

interface ScatterData {
    x: number;
    y: number;
    z?: number;
}

interface ScatterplotProps {
    data: RawData;
}

const parseData = (rawData: RawData): { wins: ScatterData[], losses: ScatterData[] } => {
    if (!rawData.wins || !rawData.losses) {
        console.error('Data is not defined:', rawData);
        return { wins: [], losses: [] };
    }

    let wins: ScatterData[] = [];
    let losses: ScatterData[] = [];
    try {
        wins = JSON.parse(rawData.wins).map((entry: any) => ({
            // z: parseFloat(entry.FinalFundsChange),
            x: Number(entry.equity),
            y: parseFloat(entry.minCall)
        }));

        losses = JSON.parse(rawData.losses).map((entry: any) => ({
            // z: parseFloat(entry.FinalFundsChange),
            x: Number(entry.equity),
            y: parseFloat(entry.minCall)
        }));
    } catch (error) {
        console.error('Error parsing the data:', error);
    }

    return { wins, losses };
}

const ScatterplotComponent: React.FC<ScatterplotProps> = ({ data }) => {
    const parsedData = parseData(data);

    return (<>
        <div className="h4">
            Wins and Losses for given equity and required minimum call
        </div>
        <VictoryChart
            domainPadding={20}
            width={800}
            height={200}
            domain={{ x: [0, 1] }, { y: [0, 2] }}
        >
            <VictoryAxis
                label="Equity"
            />
            <VictoryAxis
                dependentAxis
                label="Minimum Call"
            />
            <VictoryScatter
                data={parsedData.wins}
                x="x"
                y="y"
                size={5}  // Set a constant dot size. Adjust this value as needed.
                labels={({ datum }) => `Equity: ${datum.x}\nMinimum Call: ${datum.y}`}
                labelComponent={<VictoryTooltip />}
                style={{ data: { fill: "green" } }}
            />
            <VictoryScatter
                data={parsedData.losses}
                x="x"
                y="y"
                size={5}  // Set a constant dot size. Adjust this value as needed.
                labels={({ datum }) => `Equity: ${datum.x}\nMinimum Call: ${datum.y}`}
                labelComponent={<VictoryTooltip />}
                style={{ data: { fill: "red" } }}
            />
        </VictoryChart>
    </>
    );
}

export default ScatterplotComponent;
