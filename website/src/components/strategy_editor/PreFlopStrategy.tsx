import axios from "axios";
import React, { useEffect, useState } from "react";
import { API_URL } from "../../views/config";
import "./PreFlopStrategyEditor.css"; // Make sure the path is correct

const getBackgroundColor = (value) => {
  const hue = ((value / 100) * 120).toString(10);
  return `hsl(${hue}, 100%, 50%)`;
};

const getDefaultStrategy = () => ({
  call: 0,
  raise: 0,
  betSizeCall: "Bet Halfpot",
  betSizeRaise: "Bet Halfpot",
});


const HandScenarioRow = ({
  hand,
  scenario,
  position,
  strategies,
  onStrategyChange,
}) => {
  const [call, setCall] = useState(0);
  const [raise, setRaise] = useState(0);

  const [betSizeCall, setBetSizeCall] = useState("Bet Halfpot");
  const [betSizeRaise, setBetSizeRaise] = useState("Bet Halfpot");

  // Update call and raise when strategies or position changes
  useEffect(() => {
    const posStrategy = strategies[position]?.[hand]?.[scenario];
    setCall(posStrategy?.call || 0);
    setRaise(posStrategy?.raise || 0);
    setBetSizeCall(posStrategy?.betSizeCall || "Bet Halfpot");
    setBetSizeRaise(posStrategy?.betSizeRaise || "Bet Halfpot");
  }, [hand, scenario, position, strategies]);

  const handleBetSizeChange = (betType, value, hand, scenario) => {
    if (betType === "call") {
      setBetSizeCall(value);
      onStrategyChange(hand, scenario, call, raise, value, betSizeRaise);
    } else if (betType === "raise") {
      setBetSizeRaise(value);
      onStrategyChange(hand, scenario, call, raise, betSizeCall, value);
    }
  };
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
        <select
          value={betSizeCall}
          onChange={(e) => handleBetSizeChange("call", e.target.value)}
        >
          <option value="Bet Halfpot">1/2 Pot</option>
          <option value="Bet Pot">Pot</option>
        </select>
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
        <select
          value={betSizeRaise}
          onChange={(e) => handleBetSizeChange("raise", e.target.value)}
        >
          <option value="Bet Halfpot">1/2 Pot</option>
          <option value="Bet Pot">Pot</option>
        </select>
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

  const handleStrategyChange = (
    hand,
    scenario,
    call,
    raise,
    betSizeCall,
    betSizeRaise
  ) => {
    setStrategies((prevStrategies) => ({
      ...prevStrategies,
      [position]: {
        ...prevStrategies[position],
        [hand]: {
          ...prevStrategies[position]?.[hand],
          [scenario]: { call, raise, betSizeCall, betSizeRaise },
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
  // Handle call percentage change
  // Handle call percentage change
const handleCallChange = (event, hand, scenario) => {
  const newCall = Math.max(
    0,
    Math.min(100, parseInt(event.target.value, 10) || 0)
  );

  setStrategies((prev) => ({
    ...prev,
    [position]: {
      ...prev[position],
      [hand]: {
        ...(prev[position]?.[hand] || {}), // Initialize hand if not exists
        [scenario]: {
          ...(prev[position]?.[hand]?.[scenario] || getDefaultStrategy()), // Initialize scenario if not exists
          call: newCall,
          raise: prev[position]?.[hand]?.[scenario]?.raise || 0, // Use default if not set
          betSizeCall: prev[position]?.[hand]?.[scenario]?.betSizeCall || "Bet Halfpot", // Use default if not set
          betSizeRaise: prev[position]?.[hand]?.[scenario]?.betSizeRaise || "Bet Halfpot", // Use default if not set
        },
      },
    },
  }));
};


  // Handle raise percentage change
// Handle raise percentage change
const handleRaiseChange = (event, hand, scenario) => {
  const newRaise = Math.max(
    0,
    Math.min(100, parseInt(event.target.value, 10) || 0)
  );

  setStrategies((prev) => ({
    ...prev,
    [position]: {
      ...prev[position],
      [hand]: {
        ...(prev[position]?.[hand] || {}), // Initialize hand if not exists
        [scenario]: {
          ...(prev[position]?.[hand]?.[scenario] || getDefaultStrategy()), // Initialize scenario if not exists
          call: prev[position]?.[hand]?.[scenario]?.call || 0, // Use default if not set
          raise: newRaise,
          betSizeCall: prev[position]?.[hand]?.[scenario]?.betSizeCall || "Bet Halfpot", // Use default if not set
          betSizeRaise: prev[position]?.[hand]?.[scenario]?.betSizeRaise || "Bet Halfpot", // Use default if not set
        },
      },
    },
  }));
};

// Handle bet size change
const handleBetSizeChange = (betType, value, hand, scenario) => {
  setStrategies((prev) => ({
    ...prev,
    [position]: {
      ...prev[position],
      [hand]: {
        ...(prev[position]?.[hand] || {}), // Initialize hand if not exists
        [scenario]: {
          ...(prev[position]?.[hand]?.[scenario] || getDefaultStrategy()), // Initialize scenario if not exists
          call: prev[position]?.[hand]?.[scenario]?.call || 0, // Use default if not set
          raise: prev[position]?.[hand]?.[scenario]?.raise || 0, // Use default if not set
          [`betSize${betType[0].toUpperCase()}${betType.slice(1)}`]: value,
        },
      },
    },
  }));
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
  const getBackgroundColor = (value) => {
    // Assuming value is between 0 to 100
    const hue = ((value / 100) * 120).toString(10);
    return `hsl(${hue}, 100%, 50%)`; // From red (0) to green (120)
  };

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
            <th colSpan="5" className="left-border">
              No calls or bets
            </th>
            <th colSpan="5">1 or more calls</th>
            <th colSpan="5" className="right-border">
              1 or more raises
            </th>
          </tr>
          <tr>
            {scenarios.map((scenario, index) => (
              <React.Fragment key={scenario}>
                <th className={index > 0 ? "left-border" : ""}>% Call</th>
                <th>Call Bet Size</th>
                <th>% Raise</th>
                <th>Raise Bet Size</th>
                <th
                  className={index < scenarios.length - 1 ? "right-border" : ""}
                >
                  % Fold
                </th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {hands.map((hand) => (
            <tr key={hand}>
              <td>{hand}</td>
              
              {scenarios.map((scenario) => {
  const strategy =
    strategies[position]?.[hand]?.[scenario] || getDefaultStrategy();

  const fold = 100 - strategy.call - strategy.raise;
                return (
                  <React.Fragment key={`${hand}-${scenario}`}>
                    <td
                      className="value-cell"
                      style={{
                        backgroundColor: getBackgroundColor(strategy.call),
                      }}
                    >
                      <input
                        type="number"
                        value={strategy.call}
                        onChange={(e) => handleCallChange(e, hand, scenario)}
                        min="0"
                        max="100"
                      />
                    </td>
                    <td>
                      <select
                        value={strategy.betSizeCall}
                        onChange={(e) =>
                          handleBetSizeChange(
                            "call",
                            e.target.value,
                            hand,
                            scenario
                          )
                        }
                      >
                        <option value="Bet Halfpot">1/2 Pot</option>
                        <option value="Bet Pot">Pot</option>
                      </select>
                    </td>
                    <td
                      className="value-cell"
                      style={{
                        backgroundColor: getBackgroundColor(strategy.raise),
                      }}
                    >
                      <input
                        type="number"
                        value={strategy.raise}
                        onChange={(e) => handleRaiseChange(e, hand, scenario)}
                        min="0"
                        max="100"
                      />
                    </td>
                    <td>
                      <select
                        value={strategy.betSizeRaise}
                        onChange={(e) =>
                          handleBetSizeChange(
                            "raise",
                            e.target.value,
                            hand,
                            scenario
                          )
                        }
                      >
                        <option value="Bet Halfpot">1/2 Pot</option>
                        <option value="Bet Pot">Pot</option>
                      </select>
                    </td>
                    <td
                      className="value-cell"
                      style={{ backgroundColor: getBackgroundColor(fold) }}
                    >
                      {fold}
                    </td>
                  </React.Fragment>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// Make sure to define handleCallChange, handleRaiseChange, and handleBetSizeChange functions

export default PreFlopStrategyEditor;
