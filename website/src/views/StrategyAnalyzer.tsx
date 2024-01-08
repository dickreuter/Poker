import { CircularProgress, FormControl, InputLabel, MenuItem, Select } from '@material-ui/core';
import axios from 'axios';
import 'bootstrap/dist/css/bootstrap.min.css';
import React, { useEffect, useState } from 'react';
import GroupedStackedBarChart from '../components/GroupedBarChart';
import LeagueTablePlot from '../components/LeagueTablePlot';
import ScatterplotComponent from '../components/ScatterPlot';
import { pirate } from '../assets/Images';
import FundsChangeLineChart from '../components/FundsChangeChart';
import Loading from '../components/Loading';
import DataTable from '../components/TableData';
import { API_URL } from './config';


const StrategyAnalyzer: React.FC = () => {
    const [strategies, setStrategies] = useState<string[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);
    const [endStage, setEndStage] = useState<string>('All');
    const [actionAtEndStage, setActionAtEndStage] = useState<string>('All');
    const [barChartData, setBarChartData] = useState<any[]>([]);
    const [loadingStrategies, setLoadingStrategies] = useState<boolean>(true);
    const [loadingScatter, setLoadingScatter] = useState<boolean>(true);
    const [loadingFundsChange, setLoadingFundsChange] = useState<boolean>(true);
    const [loadingLeague, setLoadingLeague] = useState<boolean>(true);
    const [loadingBarChartData, setLoadingBarChartData] = useState<boolean>(true);
    const [loadingTable, setLoadingTable] = useState<boolean>(true);
    const [firstVisit, setFirstVisit] = useState<boolean>(true);
    const [scatterplotData, setScatterplotData] = useState<string[]>([]);
    const [fundsChangeData, setFundsChangeData] = useState<string[]>([]);
    const [tableData, setTableData] = useState<string[]>([]);
    const [leagueData, setLeagueData] = useState<any[]>([]);
    const computer_name = 'All'


    async function fetchStackedBarData() {
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
    }
    const fetchScatterplotData = async () => {
        if (selectedStrategy) {
            try {
                const response = await axios.post(`${API_URL}/get_scatterplot_data`, null, {
                    params: {
                        p_value: selectedStrategy,
                        game_stage: endStage,
                        decision: actionAtEndStage
                    }
                });
                setScatterplotData(response.data);
            } catch (error) {
                console.error("Error fetching scatterplot data:", error);
            }
            finally {
                setLoadingScatter(false); // Set loading to false after fetching scatterplot data
            }
        }
    };
    const fetchFundChangeData = async () => {
        if (selectedStrategy) {
            try {
                const response = await axios.post(`${API_URL}/get_fundschange_chart`, null, {
                    params: {
                        strategy: selectedStrategy,
                        computer_name: computer_name
                    }
                });
                setFundsChangeData(response.data);
                console.log(`Fundschange data before passing: ${JSON.stringify(fundsChangeData)}`);
            } catch (error) {
                console.error("Error fetching fundschange chart:", error);
            }
            finally {
                setLoadingFundsChange(false); // Set loading to false after fetching fundschange data
            }
        }
    };
    const fetchTableData = async () => {
        if (selectedStrategy) {
            try {
                const response = await axios.post(`${API_URL}/get_worst_games`, null, {
                    params: {
                        strategy: selectedStrategy,
                    }
                });
                setTableData(response.data);
                console.log(`Tabledata data before passing: ${JSON.stringify(fundsChangeData)}`);
            } catch (error) {
                console.error("Error fetching tabledata:", error);
            }
            finally {
                setLoadingTable(false);
            }
        }
    };

    useEffect(() => {
        async function fetchLeagueData() {
            try {
                const response = await axios.post(`${API_URL}/get_top_strategies`);
                setLeagueData(response.data);
                // console.log(`League data: ${JSON.stringify(response.data)}`);
            } catch (error) {
                console.error("Error fetching league data:", error);
            } finally {
                setLoadingLeague(false);
            }
        }
        fetchLeagueData();
    }, []);


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
        fetchStackedBarData();
        fetchScatterplotData();
        fetchFundChangeData();
        fetchTableData();
    }, [selectedStrategy, endStage, actionAtEndStage]);

    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        setLoadingBarChartData(true);
        setLoadingScatter(true);
        setLoadingTable(true);
        setLoadingFundsChange(true);
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
            <div className="pt-2">
                {loadingBarChartData && firstVisit ? (
                    // <div className='rotating'>
                    <div>

                        {loadingLeague ? (
                            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
                                <img src={pirate} style={{ transform: 'scale(.7)' }} />
                            </div>
                        ) : (
                            <>
                                <div className="h3" role="status">
                                    Strategy league table by strategy and user
                                </div>
                                <LeagueTablePlot data={leagueData} />
                            </>
                        )
                        }
                    </div>
                ) : loadingBarChartData ? (
                    <Loading />
                ) : (
                    <div style={{ marginTop: '20px' }}>
                        {barChartData.length > 0 && <GroupedStackedBarChart data={JSON.parse(barChartData)} />}
                    </div>
                )
                }
            </div>
            <div className="pt-5">
                {
                    loadingScatter ? (
                        !firstVisit ? (
                            <Loading />
                        ) : (<></>)
                    ) : (
                        <div style={{ marginTop: '20px' }}>
                            <ScatterplotComponent data={scatterplotData} />
                        </div>
                    )
                }
            </div>
            <div className="pt-5">
                {
                    loadingFundsChange ? (
                        !firstVisit ? (
                            <Loading />
                        ) : (<></>)
                    ) : (
                        <div style={{ marginTop: '20px' }}>
                            <FundsChangeLineChart data={fundsChangeData} />
                        </div>
                    )
                }
            </div>
            <div className="pt-5">
                {
                    loadingTable ? (
                        !firstVisit ? (
                            <Loading />
                        ) : (<></>)
                    ) : (
                        <div style={{ marginTop: '20px' }}>
                            <DataTable data={tableData} />
                        </div>
                    )
                }
            </div>

        </div >
    );
};

export default StrategyAnalyzer;
