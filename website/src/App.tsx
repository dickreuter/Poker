import ReactGA from "react-ga";
import { BrowserRouter } from "react-router-dom";
import "./App.css";
import NavBar from "./routes/NavBar";
import Routing from "./routes/Routing";
import { useEffect } from "react";

const TRACKING_ID = "UA-7794836-7"; // OUR_TRACKING_ID
ReactGA.initialize(TRACKING_ID);

function App() {
  useEffect(() => {
    ReactGA.pageview(window.location.pathname + window.location.search);
  }, []);

  return (
    <>
      <BrowserRouter>
        <NavBar />
        <div className="main-content">
          <Routing />
        </div>
      </BrowserRouter>
    </>
  );
}

export default App;
