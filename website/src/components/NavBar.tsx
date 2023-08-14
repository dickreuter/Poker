import 'bootstrap/dist/css/bootstrap.css';
import { Link } from "react-router-dom";

function NavBar() {
    return (
        <nav className="navbar navbar-expand-sm fixed-top navbar-light bg-light">
            <button className="navbar-toggler" type="button" data-toggle="collapse" data-target="#navbarText" aria-controls="navbarText" aria-expanded="false" aria-label="Toggle navigation">
                <span className="navbar-toggler-icon"></span>
            </button>
            <a className="navbar-brand" href="/">DeeperMind PokerBot</a>

            <div className="collapse navbar-collapse" id="navbarTogglerDemo03">
                <ul className="navbar-nav mr-auto">
                    <li className="nav-item">
                        <a className="nav-link" href="https://onedrive.live.com/download?cid=A3B69BDCC03E82A9&resid=A3B69BDCC03E82A9%21111289&authkey=AEftpEpz8jxnBdI">Download</a>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/purchase">Purchase</Link>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/strategyanalyzer">Strategy Analyzer</Link>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/tableanalyzer">Table Analyzer</Link>
                    </li>

                    <li className="nav-item">
                        <a className="nav-link" href="https://discord.gg/xB9sR3Q7r3">Support chat</a>
                    </li>
                    <li className="nav-item">
                        <a className="nav-link" href="https://github.com/dickreuter/Poker">Source code</a>
                    </li>
                    <li className="nav-item">
                        <a className="nav-link" href="https://github.com/dickreuter/Poker/blob/master/readme.rst">Documentation</a>
                    </li>
                </ul>
            </div>
        </nav>
    )
}

export default NavBar