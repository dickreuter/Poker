import ReactGA from "react-ga";
import { BrowserRouter } from "react-router-dom";
import "./App.css";
import NavBar from "./routes/NavBar";
import Routing from "./routes/Routing";
import { useEffect } from "react";
import ReactGA4 from "react-ga4";

ReactGA4.initialize("G-H40Z0W36GF");

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
