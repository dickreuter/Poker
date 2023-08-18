
import { Route, Routes } from "react-router-dom"
import Home from "../views/Home"
import PaymentCards from "../views/Purchase"
import TableAnalyzer from "../views/TableAnalyzer"
import StrategyAnalyzer from "../views/StrategyAnalyzer"

function Routing() {
    return (
        <div>
            <Routes>
                <Route path="strategyanalyzer" element={<StrategyAnalyzer />} />
                <Route path="tableanalyzer" element={<TableAnalyzer />} />
                <Route path="/" element={<Home />} />
                <Route path="/purchase" element={<PaymentCards />} />
            </Routes>
        </div>
    )
}

export default Routing