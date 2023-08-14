import { CircularProgress, FormControl, InputLabel, MenuItem, Select } from '@material-ui/core';
import axios from 'axios';
import 'bootstrap/dist/css/bootstrap.min.css';
import React, { useEffect, useState } from 'react';
import { pirate } from '../assets/Images';
import GroupedStackedBarChart from './GroupedBarChart';


const StrategyAnalyzer: React.FC = () => {
    const API_URL = import.meta.env.REACT_APP_API_URL || 'http://dickreuter.com:7777';
    const [strategies, setStrategies] = useState<string[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);
    const [endStage, setEndStage] = useState<string>('All');
    const [actionAtEndStage, setActionAtEndStage] = useState<string>('All');
    const [barChartData, setBarChartData] = useState<any[]>([]);
    const [loadingStrategies, setLoadingStrategies] = useState<boolean>(true);
    const [loadingBarChartData, setLoadingBarChartData] = useState<boolean>(true);
    const [firstVisit, setFirstVisit] = useState<boolean>(true);


    const fetchData = async () => {
        if (selectedStrategy) {
            try {
                const response = await axios.post(`${API_URL}/get_stacked_bar_data_react`, null, {
                    params: {
                        p_value: selectedStrategy,
                        chartType: 'All',
                        last_stage: endStage,
                        last_action: actionAtEndStage,
                        computer_name: 'All',
                    }
                });
                setBarChartData(response.data);
            } catch (error) {
                console.error("Error fetching bar chart data:", error);
            } finally {
                setLoadingBarChartData(false); // Set loading to false after fetching bar chart data
            }
        }
    };

    useEffect(() => {
        async function fetchStrategies() {
            try {
                const response = await axios.post<string[]>(`${API_URL}/get_played_strategy_list`, null, {
                    params: {
                        login: 'YOUR_LOGIN',
                        password: 'YOUR_PASSWORD',
                        computer_name: 'YOUR_COMPUTER_NAME'
                    }
                });
                setStrategies(response.data);
            } catch (error) {
                console.error("Error fetching strategies:", error);
            } finally {
                setLoadingStrategies(false); // Set loading to false after fetching strategies
            }
        }
        fetchStrategies();
    }, []);

    useEffect(() => {
        fetchData();
    }, [selectedStrategy, endStage, actionAtEndStage]);

    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        setLoadingBarChartData(true);
        setFirstVisit(false);
        setSelectedStrategy(event.target.value);
    };

    const handleEndStageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        setEndStage(event.target.value);
    };

    const handleActionAtEndStageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        setActionAtEndStage(event.target.value);
    };

    return (
        <div className="barchart">
            <div className="dropdowns-container">
                <FormControl variant="outlined" style={{ width: '200px', marginRight: '10px' }}>
                    <InputLabel id="strategy-label">Select a strategy</InputLabel>
                    <Select
                        labelId="strategy-label"
                        value={selectedStrategy || ''}
                        onChange={handleChange}
                        label="Select a strategy"
                    >
                        {strategies.map((strategy) => (
                            <MenuItem key={strategy} value={strategy}>
                                {strategy}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>

                <FormControl variant="outlined" style={{ width: '150px', marginRight: '10px' }}>
                    <InputLabel id="end-stage-label">End Stage</InputLabel>
                    <Select
                        labelId="end-stage-label"
                        value={endStage}
                        onChange={handleEndStageChange}
                        label="End Stage"
                    >
                        {['All', 'PreFlop', 'Flop', 'Turn', 'River'].map(stage => (
                            <MenuItem key={stage} value={stage}>
                                {stage}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>

                <FormControl variant="outlined" style={{ width: '200px' }}>
                    <InputLabel id="action-label">Action at End Stage</InputLabel>
                    <Select
                        labelId="action-label"
                        value={actionAtEndStage}
                        onChange={handleActionAtEndStageChange}
                        label="Action at End Stage"
                    >
                        {['All', 'Check', 'Call', 'Bet', 'Bet Bluff', 'BetPlus', 'Bet half pot', 'Bet pot'].map(action => (
                            <MenuItem key={action} value={action}>
                                {action}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
            </div>
            {loadingBarChartData && firstVisit ? (
                // <div className='rotating'>
                <div>
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
                        <img src={pirate} style={{ transform: 'scale(.7)' }} />
                    </div>
                </div>
            ) :
                loadingBarChartData ? (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
                        <CircularProgress />
                    </div>
                ) :
                    (<div style={{ marginTop: '20px' }}>
                        {barChartData.length > 0 && <GroupedStackedBarChart data={JSON.parse(barChartData)} />}
                    </div>)}


        </div>
    );
};

export default StrategyAnalyzer;
