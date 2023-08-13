import { BrowserRouter, Route, Routes } from "react-router-dom"
import './App.css'
import NavBar from './components/NavBar'
import PaymentCards from './components/PaymentCards'
import StrategyAnalyzer from './components/StrategyAnalyzer'
import TableAnalyzer from './components/TableAnalyzer'
import Home from "./components/Home"


function App() {

  return (
    <>
      <BrowserRouter>
      <NavBar />
      <Routes>
          <Route path="strategyanalyzer" element={<StrategyAnalyzer />} />
          <Route path="tableanalyzer" element={<TableAnalyzer />} />
          <Route path="/" element={<Home />} />
          <Route path="/purchase" element={<PaymentCards />} />
      </Routes>
    </BrowserRouter>
    </>
  )
}

export default App
