import { Tab, Tabs } from "@mui/material";
import axios from "axios";
import "bootstrap/dist/css/bootstrap.css";
import React, { useEffect, useRef, useState } from "react";
import { Dropdown } from "react-bootstrap";
import "./TableMapper.css";
import { API_URL } from "./config";

function TableMapper() {
  const canvasRef = useRef(null);
  const previewRef = useRef(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [screenshot, setScreenshot] = useState(null);
  const [lastSelection, setLastSelection] = useState(null);
  const [currentSelection, setCurrentSelection] = useState({
    start: { x: 0, y: 0 },
    end: { x: 0, y: 0 },
  });
  const [cardImages, setCardImages] = useState({});
  const [loading, setLoading] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [computerName, setComputerName] = useState("");
  const [tableNames, setTableNames] = useState([]);
  const [lastSelectedTableName, setLastSelectedTableName] =
    useState("Load Template");
  const suits = ["c", "d", "h", "s"]; // Clubs, Diamonds, Hearts, Spades
  const ranks = [
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "T",
    "J",
    "Q",
    "K",
    "A",
  ];
  const [buttonImages, setButtonImages] = useState({});
  const [buttonSelections, setButtonSelections] = useState({});

  // Add this function to handle the saving of button selections
  const saveButtonSelection = async (imageData, label) => {
    try {
      // Here you would send imageData and label to your backend
      const response = await axios.post(`${API_URL}/save_button_selection`, {
        image_data: imageData,
        label: label,
      });
      console.log("Button selection saved:", response.data);
    } catch (error) {
      console.error("Error saving button selection:", error);
    }
  };

  // Call this function when the 'save' button is clicked
  const onSaveButtonClick = (buttonKey) => {
    const selection = buttonSelections[buttonKey];
    const image = buttonImages[buttonKey];
    if (selection && image) {
      saveButtonSelection(image, buttonKey);
    } else {
      console.error("No selection or image to save for button:", buttonKey);
    }
  };

  const takeScreenshot = async () => {
    try {
      console.log("taking screenshot");
      setLoading(true); // start the loading spinner

      // Use axios to make the request
      const response = await axios.get(
        "http://127.0.0.1:8005/take_screenshot",
        {
          responseType: "blob", // Important to handle binary data
        }
      );

      const imageUrl = URL.createObjectURL(response.data);
      setScreenshot(imageUrl);
      setLoading(false); // stop the loading spinner
    } catch (error) {
      console.error("Error fetching screenshot:", error);
      setLoading(false); // stop the loading spinner in case of error
    }
  };

  const saveSelection = async (imageData, label, tableName) => {
    try {
      const response = await axios.post(`${API_URL}/update_state`, {
        state: imageData, // Assuming this is the format your backend expects
        label: label,
        table_name: tableName,
      });
      // Handle successful save here
      console.log("Selection saved:", response.data);
    } catch (error) {
      console.error("Error saving selection:", error);
    }
  };

  const fetchAvailableTables = async () => {
    try {
      const response = await axios.post(
        `${API_URL}/get_available_tables`,
        null, // No body for the POST request
        {
          params: {
            computer_name: computerName,
          },
        }
      );
      setTableNames(response.data); // Set the fetched table names
    } catch (error) {
      console.error("Error fetching available tables:", error);
    }
  };

  const loadTable = async (tableName) => {
    try {
      setLastSelectedTableName(tableName);
      const response = await axios.post(
        `${API_URL}/get_table`,
        null, // No body for the POST request
        {
          params: {
            table_name: tableName,
          },
        }
      );

      console.log("Table data:", response.data);

      const newCardImages = {};
      Object.keys(response.data).forEach((key) => {
        // Regex to match card data keys (e.g., '2c', '3d', etc.)
        if (/^[2-9TJQKA][cdhs]$/.test(key)) {
          newCardImages[key] = `data:image/png;base64,${response.data[key]}`;
        }
      });
      setCardImages(newCardImages);
    } catch (error) {
      console.error("Error loading table:", error);
    }
  };

  const fetchComputerName = async () => {
    try {
      const response = await axios.get(
        "http://127.0.0.1:8005/get_computer_name"
      );
      setComputerName(response.data.computer_name);
    } catch (error) {
      console.error("Error fetching computer name:", error);
    }
  };

  useEffect(() => {
    fetchComputerName();
    // ... (rest of your useEffect logic for screenshot)
  }, []);

  useEffect(() => {
    if (computerName) {
      fetchAvailableTables();
    }
  }, [computerName]);

  useEffect(() => {
    if (screenshot) {
      const ctx = canvasRef.current.getContext("2d");
      const img = new Image();
      img.src = screenshot;
      img.onload = () => {
        ctx.canvas.width = img.width;
        ctx.canvas.height = img.height;
        ctx.drawImage(img, 0, 0);

        if (lastSelection) {
          ctx.strokeStyle = "red";
          ctx.strokeRect(
            lastSelection.start.x,
            lastSelection.start.y,
            lastSelection.end.x - lastSelection.start.x,
            lastSelection.end.y - lastSelection.start.y
          );

          const previewCtx = previewRef.current.getContext("2d");
          const selectionWidth = lastSelection.end.x - lastSelection.start.x;
          const selectionHeight = lastSelection.end.y - lastSelection.start.y;

          // Set the preview canvas dimensions to the selection dimensions
          previewCtx.canvas.width = selectionWidth;
          previewCtx.canvas.height = selectionHeight;

          // Draw the image using the original dimensions, not scaled
          previewCtx.drawImage(
            img,
            lastSelection.start.x,
            lastSelection.start.y,
            selectionWidth,
            selectionHeight,
            0,
            0,
            selectionWidth,
            selectionHeight
          );
        }
      };
    }
  }, [screenshot, lastSelection]);

  const handleMouseDown = (e) => {
    setIsDrawing(true);
    setCurrentSelection({
      start: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY },
      end: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY },
    });
  };

  const handleMouseUp = (e) => {
    setIsDrawing(false);
    setLastSelection(currentSelection);
  };

  const handleMouseMove = (e) => {
    if (!isDrawing) return;

    const newSelection = {
      ...currentSelection,
      end: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY },
    };

    setCurrentSelection(newSelection);
    redrawCanvas(newSelection);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = async (e) => {
    e.preventDefault();

    // Check if files were dragged and dropped
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];

      // Check if the file is an image
      if (file.type.startsWith("image/")) {
        const imageUrl = URL.createObjectURL(file);
        setScreenshot(imageUrl);
      }
    }
  };

  const redrawCanvas = (newSelection) => {
    const ctx = canvasRef.current.getContext("2d");
    const img = new Image();
    img.src = screenshot;
    img.onload = () => {
      ctx.drawImage(img, 0, 0);

      // Draw new selection
      ctx.strokeStyle = "red";
      ctx.lineWidth = 2;
      ctx.strokeRect(
        newSelection.start.x,
        newSelection.start.y,
        newSelection.end.x - newSelection.start.x,
        newSelection.end.y - newSelection.start.y
      );
    };
  };

  const handleTabChange = (event: SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <div className="container toplevel-container">
      <div className="row">
        <div className="col-8">
          <div className="container">
            <div className="row">
              <div className="col-3">{/* <div className="tm_button"> */}</div>
            </div>
            <div className="row">
              <div className="col-3">
                <Dropdown>
                  <Dropdown.Toggle variant="primary" className="tm_button">
                    {lastSelectedTableName}{" "}
                    {/* Dynamic label based on selection */}
                  </Dropdown.Toggle>
                  <Dropdown.Menu className="scrollable-dropdown-menu">
                    {tableNames.map((tableName, index) => (
                      <Dropdown.Item
                        key={index}
                        onClick={() => loadTable(tableName)}
                      >
                        {tableName}
                      </Dropdown.Item>
                    ))}
                  </Dropdown.Menu>
                </Dropdown>
              </div>
              <div className="col-3">
                <button className="btn btn-secondary tm_button">
                  Delete template
                </button>
              </div>
              <div className="col-3">
                <button className="btn btn-success tm_button">Blank new</button>
              </div>
              <div className="col-3">
                <button className="btn btn-success tm_button">
                  Copy to new
                </button>
              </div>
            </div>

            <div className="row">
              <div className="col-3">
                <button
                  className="btn btn-primary tm_button"
                  onClick={takeScreenshot}
                >
                  Take Screenshot
                </button>
              </div>
              <div className="col-3">
                <button className="btn btn-primary tm_button">
                  Crop top left corner
                </button>
              </div>
              <div className="col-3">
                <button className="btn btn-danger tm_button">
                  Save new top left corner
                </button>
              </div>
            </div>
            {/* <div className="row">
                <div className="col-12">
                    <div className="screenshotWindow">
                        <canvas ref={previewRef}></canvas>
                    </div>
                </div>
            </div> */}
            <div className="row mt-3">
              <div className="col-12 previewWindow">
                {loading ? (
                  <div
                    className="d-flex justify-content-center align-items-center"
                    style={{ height: "100%" }}
                  >
                    <div className="spinner-border text-primary" role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                  </div>
                ) : (
                  <canvas
                    ref={canvasRef}
                    onMouseDown={handleMouseDown}
                    onMouseUp={handleMouseUp}
                    onMouseMove={handleMouseMove}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                  ></canvas>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="col-4">
          <div className="container">
            <div className="row">
              <div className="col-12">
                <Tabs
                  value={tabValue}
                  onChange={handleTabChange}
                  aria-label="tab example"
                >
                  <Tab label="Buttons" />
                  <Tab label="Players" />
                  <Tab label="Cards" />
                  <Tab label="Mouse" />
                  <Tab label="Test" />
                </Tabs>

                {tabValue === 0 && (
                  <div className="buttons-grid">
                    {/* Map over your buttons data here */}
                    {Object.entries(buttonImages).map(
                      ([buttonKey, imageSrc]) => (
                        <div key={buttonKey} className="button-image">
                          <img src={imageSrc} alt={buttonKey} />
                          <button
                            className="save-selection-button"
                            onClick={() => onSaveButtonClick(buttonKey)}
                          >
                            Save
                          </button>
                        </div>
                      )
                    )}
                  </div>
                )}
                {tabValue === 1 && <div>{/* Content for "Players" tab */}</div>}
                {tabValue === 2 && (
                  <div className="cards-grid">
                    {ranks.map((rank) => (
                      <React.Fragment key={rank}>
                        {suits.map((suit) => {
                          const cardKey = rank + suit;
                          return (
                            <div key={cardKey} className="card-image">
                              {cardImages[cardKey] && (
                                <img src={cardImages[cardKey]} alt={cardKey} />
                              )}
                              <button
                                className="save-selection-button"
                                onClick={() =>
                                  saveSelection(
                                    cardImages[cardKey],
                                    cardKey,
                                    lastSelectedTableName
                                  )
                                }
                              >
                                Save
                              </button>
                            </div>
                          );
                        })}
                      </React.Fragment>
                    ))}
                  </div>
                )}

                {tabValue === 3 && <div>{/* Content for "Mouse" tab */}</div>}
                {tabValue === 4 && <div>{/* Content for "Test" tab */}</div>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default TableMapper;
