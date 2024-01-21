import axios from "axios";
import React, { useEffect, useState } from "react";
import { API_URL } from "../../views/config";

// Subcomponent for each hand scenario row
const HandScenarioRow = ({
  hand,
  scenario,
  position,
  strategies,
  onStrategyChange,
}) => {
  const [call, setCall] = useState(0);
  const [raise, setRaise] = useState(0);

  // Update call and raise when strategies or position changes
  useEffect(() => {
    const posStrategy = strategies[position]?.[hand]?.[scenario];
    setCall(posStrategy?.call || 0);
    setRaise(posStrategy?.raise || 0);
  }, [hand, scenario, position, strategies]);

  const handleCallChange = (e) => {
    const newCall = Math.max(
      0,
      Math.min(100, parseInt(e.target.value, 10) || 0)
    );
    onStrategyChange(hand, scenario, newCall, raise);
  };

  const handleRaiseChange = (e) => {
    const newRaise = Math.max(
      0,
      Math.min(100, parseInt(e.target.value, 10) || 0)
    );
    onStrategyChange(hand, scenario, call, newRaise);
  };

  const fold = 100 - call - raise;

  return (
    <>
      <td>
        <input
          type="number"
          value={call}
          onChange={handleCallChange}
          min="0"
          max="100"
        />
        %
      </td>
      <td>
        <input
          type="number"
          value={raise}
          onChange={handleRaiseChange}
          min="0"
          max="100"
        />
        %
      </td>
      <td>{`${fold}%`}</td>
    </>
  );
};

// Main component
const PreFlopStrategyEditor = () => {
  const [position, setPosition] = useState("0");
  const [strategies, setStrategies] = useState({});

  useEffect(() => {
    const fetchPreflopValues = async () => {
      try {
        const response = await axios.get(
          `${API_URL}/get_preflop_values/default`
        );
        setStrategies(response.data.preflop_values || {});
      } catch (error) {
        console.error("Error fetching preflop values:", error);
        // Handle the error
      }
    };

    fetchPreflopValues();
  }, []);

  const handleStrategyChange = (hand, scenario, call, raise) => {
    setStrategies((prevStrategies) => ({
      ...prevStrategies,
      [position]: {
        ...prevStrategies[position],
        [hand]: {
          ...prevStrategies[position]?.[hand],
          [scenario]: { call, raise },
        },
      },
    }));
  };

  const handlePositionChange = (e) => {
    setPosition(e.target.value);
  };

  // Function to save all strategies for all positions
  const saveStrategy = async () => {
    try {
      const response = await axios.post(`${API_URL}/save_preflop_values`, {
        table_name: "default", // This could be a dynamic name based on your application logic
        preflop_values: strategies, // Sending the entire strategies object
      });

      if (response.data.message) {
        console.log(response.data.message);
        // Optionally, display a success message to the user
      }
    } catch (error) {
      console.error("Error saving preflop values:", error);
      // Optionally, display an error message to the user
    }
  };

  const scenarios = ["noCalls", "previousCalls", "previousRaises"];
  const hands = [
    "AA",
    "KK",
    "QQ",
    "JJ",
    "TT",
    "99",
    "88",
    "77",
    "66",
    "55",
    "44",
    "33",
    "22",
    "AKs",
    "AQs",
    "AJs",
    "ATs",
    "A9s",
    "A8s",
    "A7s",
    "A6s",
    "A5s",
    "A4s",
    "A3s",
    "A2s",
    "KQs",
    "KJs",
    "KTs",
    "K9s",
    "K8s",
    "K7s",
    "K6s",
    "K5s",
    "K4s",
    "K3s",
    "QJs",
    "QTs",
    "Q9s",
    "JTs",
    "J9s",
    "J8s",
    "T9s",
    "T8s",
    "T7s",
    "98s",
    "97s",
    "96s",
    "87s",
    "86s",
    "85s",
    "76s",
    "75s",
    "74s",
    "65s",
    "64s",
    "63s",
    "54s",
    "53s",
    "52s",
    "43s",
    "42s",
    "AKo",
    "AJo",
    "ATo",
    "KQo",
    "KJo",
    "QJo",
  ];

  return (
    <div>
      <label>
        Position:
        <select value={position} onChange={handlePositionChange}>
          {Array.from({ length: 10 }, (_, i) => (
            <option key={i} value={String(i)}>
              {i}
            </option>
          ))}
        </select>
      </label>
      <button onClick={saveStrategy}>Save</button>
      <table>
        <thead>
          <tr>
            <th>Hand</th>
            <th colSpan="3">No calls or raises</th> {/* Colspan of 3 for the scenario grouping */}
            <th colSpan="3">1 or more calls</th>    {/* Colspan of 3 for the scenario grouping */}
            <th colSpan="3">1 or more raises</th>   {/* Colspan of 3 for the scenario grouping */}
          </tr>
          <tr>
            {scenarios.map((scenario) => (
              <React.Fragment key={scenario}>
                <th>Call</th>
                <th>Raise</th>
                <th>Fold</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {hands.map((hand) => (
            <tr key={hand}>
              <td>{hand}</td>
              {scenarios.map((scenario) => (
                <HandScenarioRow
                  key={`${hand}-${scenario}`}
                  hand={hand}
                  scenario={scenario}
                  position={position}
                  strategies={strategies}
                  onStrategyChange={handleStrategyChange}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PreFlopStrategyEditor;
