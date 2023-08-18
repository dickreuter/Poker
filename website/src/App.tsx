import { BrowserRouter, Route, Routes } from "react-router-dom"
import './App.css'
import NavBar from './routes/NavBar'
import PaymentCards from './views/Purchase'
import StrategyAnalyzer from './views/StrategyAnalyzer'
import TableAnalyzer from './views/TableAnalyzer'
import Home from "./views/Home"
import Routing from "./routes/Routing"


function App() {

  return (
    <>
      <BrowserRouter>
      <NavBar />
      <Routing/>
    </BrowserRouter>
    </>
  )
}

export default App
