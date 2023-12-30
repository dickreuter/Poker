import React, { useState, useEffect } from 'react';

function DataTable({ data }) {
  const [filteredData, setFilteredData] = useState(data);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  useEffect(() => {
    let resultData = [...data];

    // Filter logic
    if (searchTerm) {
      resultData = resultData.filter(row =>
        Object.values(row).some(value =>
          String(value).toLowerCase().includes(searchTerm.toLowerCase())
        )
      );
    }

    // Sort logic
    if (sortConfig.key) {
      const directionMultiplier = sortConfig.direction === 'asc' ? 1 : -1;
      resultData.sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
          return -1 * directionMultiplier;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
          return 1 * directionMultiplier;
        }
        return 0;
      });
    }

    setFilteredData(resultData);
  }, [searchTerm, sortConfig, data]);

  const toggleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  }

  return (
    <div>
      {/* Search input */}
      {/* <input
        type="text"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        placeholder="Filter table..."
      /> */}
      <div className="h4">
        Worst Hands
      </div>
      <table>
        <thead>
          <tr>
            {data.length > 0 && Object.keys(data[0]).map((key) => (
              <th key={key} onClick={() => toggleSort(key)}>
                {key} {sortConfig.key === key ? (sortConfig.direction === 'asc' ? '🔼' : '🔽') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filteredData.map((row, index) => (
            <tr key={index}>
              {Object.entries(row).map(([key, value], idx) => (
                <td key={idx}>
                  {key === 'Loss' ? value.toFixed(2) : value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
