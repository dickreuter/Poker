import { Tab, Tabs } from '@mui/material';
import 'bootstrap/dist/css/bootstrap.css';
import { useEffect, useRef, useState } from 'react';
import { Dropdown } from 'react-bootstrap';
import './TableMapper.css';


function TableMapper() {
    const canvasRef = useRef(null);
    const previewRef = useRef(null);
    const [isDrawing, setIsDrawing] = useState(false);
    const [screenshot, setScreenshot] = useState(null);
    const [lastSelection, setLastSelection] = useState(null);
    const [currentSelection, setCurrentSelection] = useState({ start: { x: 0, y: 0 }, end: { x: 0, y: 0 } });
    const [loading, setLoading] = useState(false);
    const [tabValue, setTabValue] = useState(0);


    const takeScreenshot = async () => {
        try {
            console.log("taking screenshot")
            setLoading(true); // start the loading spinner
            const response = await fetch('http://localhost:8005/take_screenshot');
            const imageBlob = await response.blob();
            const imageUrl = URL.createObjectURL(imageBlob);
            setScreenshot(imageUrl);
            setLoading(false); // stop the loading spinner
        } catch (error) {
            console.error("Error fetching screenshot:", error);
            setLoading(false); // stop the loading spinner in case of error
        }
    };


    useEffect(() => {
        if (screenshot) {
            const ctx = canvasRef.current.getContext('2d');
            const img = new Image();
            img.src = screenshot;
            img.onload = () => {
                ctx.canvas.width = img.width;
                ctx.canvas.height = img.height;
                ctx.drawImage(img, 0, 0);

                if (lastSelection) {
                    ctx.strokeStyle = 'red';
                    ctx.strokeRect(
                        lastSelection.start.x, lastSelection.start.y,
                        lastSelection.end.x - lastSelection.start.x, lastSelection.end.y - lastSelection.start.y
                    );

                    const previewCtx = previewRef.current.getContext('2d');
                    const selectionWidth = lastSelection.end.x - lastSelection.start.x;
                    const selectionHeight = lastSelection.end.y - lastSelection.start.y;

                    // Set the preview canvas dimensions to the selection dimensions
                    previewCtx.canvas.width = selectionWidth;
                    previewCtx.canvas.height = selectionHeight;

                    // Draw the image using the original dimensions, not scaled
                    previewCtx.drawImage(
                        img,
                        lastSelection.start.x, lastSelection.start.y,
                        selectionWidth, selectionHeight,
                        0, 0, selectionWidth, selectionHeight
                    );
                }
            };
        }
    }, [screenshot, lastSelection]);

    const handleMouseDown = (e) => {
        setIsDrawing(true);
        setCurrentSelection({
            start: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY },
            end: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY }
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
            end: { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY }
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
            if (file.type.startsWith('image/')) {
                const imageUrl = URL.createObjectURL(file);
                setScreenshot(imageUrl);
            }
        }
    };
    

    const redrawCanvas = (newSelection) => {
        const ctx = canvasRef.current.getContext('2d');
        const img = new Image();
        img.src = screenshot;
        img.onload = () => {
            ctx.drawImage(img, 0, 0);

            // Draw new selection
            ctx.strokeStyle = 'red';
            ctx.lineWidth = 2;
            ctx.strokeRect(
                newSelection.start.x, newSelection.start.y,
                newSelection.end.x - newSelection.start.x, newSelection.end.y - newSelection.start.y
            );
        };
    };

    function handleChange(event: SyntheticEvent<Element, Event>, value: any): void {
        setTabValue(value);
    }

    return (
        <div className="container toplevel-container">
            <div className="row">
                <div className="col-8">
                    <div className="container">
                        <div className="row">
                            <div className="col-3">
                                {/* <div className="tm_button"> */}
                                <Dropdown>
                                    <Dropdown.Toggle variant="primary" className="tm_button">
                                        Load template template
                                    </Dropdown.Toggle>
                                    <Dropdown.Menu>
                                        <Dropdown.Item href="#">Action</Dropdown.Item>
                                        <Dropdown.Item href="#">Another action</Dropdown.Item>
                                        <Dropdown.Item href="#">Something else here</Dropdown.Item>
                                    </Dropdown.Menu>
                                </Dropdown>
                            </div>

                        </div>
                        <div className="row">
                            <div className="col-3">
                                <button className="btn btn-primary tm_button">Load table template</button>
                            </div>
                            <div className="col-3">
                                <button className="btn btn-secondary tm_button">Delete template</button>
                            </div>
                            <div className="col-3">
                                <button className="btn btn-success tm_button">Blank new</button>
                            </div>
                            <div className="col-3">
                                <button className="btn btn-success tm_button">Copy to new</button>
                            </div>
                        </div>

                        <div className='row'>
                            <div className="col-3">
                                <button className="btn btn-primary tm_button" onClick={takeScreenshot}>Take Screenshot</button>
                            </div>
                            <div className="col-3">
                                <button className="btn btn-primary tm_button">Crop top left corner</button>
                            </div>
                            <div className="col-3">
                                <button className="btn btn-danger tm_button">Save new top left corner</button>
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
                                    <div className="d-flex justify-content-center align-items-center" style={{ height: '100%' }}>
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

                                <Tabs value={tabValue} onChange={handleChange} aria-label="disabled tabs example">
                                    <Tab label="Buttons" />
                                    <Tab label="Players" />
                                    <Tab label="Cards" />
                                    <Tab label="Mouse" />
                                    <Tab label="Test" />
                                </Tabs>



                            </div>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}

export default TableMapper;
