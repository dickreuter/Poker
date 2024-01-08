import { CircularProgress } from '@mui/material';
import axios from 'axios';
import 'bootstrap/dist/css/bootstrap.css';
import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, Tooltip, XAxis, YAxis } from 'recharts';
import { API_URL } from './config';

function TableAnalyzer() {
  const [tableData, setTableData] = useState([]);
  const [loading, setLoading] = useState(true); // New state for loading

  useEffect(() => {
    async function fetchData() {
      try {
        const result = await axios.post(`${API_URL}/get_table_stats`, null, {
          params: {
            computer_name: 'YOUR_COMPUTER_NAME'
          }
        });
        setTableData(result.data);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setLoading(false); // Set loading to false once fetching is done (either success or error)
      }
    }
    fetchData();
  }, []);

  const data = tableData.map(table => ({ name: table.table_name, plays: table._plays }));

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </div>
    );
  }

  return (
    <div className="tablechart">
      <div className="h4">Recently used table mappings</div>
      <BarChart width={600} height={900} data={data} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" />
        <YAxis
          dataKey="name"
          type="category"
          width={100}
          tick={{ fontSize: 8 }}
        />
        <XAxis
          type="number"
          allowDataOverflow={true}
          tick={{ fontSize: 8 }}
        />
        <Tooltip />
        <Legend />
        <Bar dataKey="plays" fill="#8884d8" />
      </BarChart>
    </div>
  );
}

export default TableAnalyzer;
