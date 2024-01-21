import React, { useState } from 'react';
import 'bootstrap/dist/css/bootstrap.css';
import { Link } from 'react-router-dom';
import { useDlLink } from '../views/config';

function NavBar() {
    // State to manage the toggle status of the navbar
    const [isOpen, setIsOpen] = useState(false);
    const dlLink = useDlLink();

    // Function to toggle the navbar
    const toggle = () => {
        setIsOpen(!isOpen);
    };

    return (
        <nav className="navbar navbar-expand-sm fixed-top navbar-light bg-light">
            <button
                className="navbar-toggler"
                type="button"
                onClick={toggle} // Toggle the navbar on click
                aria-label="Toggle navigation"
            >
                <span className="navbar-toggler-icon"></span>
            </button>
            <a className="navbar-brand" href="/">
                DeeperMind PokerBot
            </a>

            <div className={`collapse navbar-collapse ${isOpen ? 'show' : ''}`} id="navbarTogglerDemo03">
                <ul className="navbar-nav mr-auto">
                    <li className="nav-item">
                        <a className="nav-link" href={dlLink}>
                            Download
                        </a>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/purchase">
                            Purchase
                        </Link>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/strategyanalyzer">
                            Strategies
                        </Link>
                    </li>
                    <li className="nav-item">
                        <Link className="nav-link" to="/tableanalyzer">
                            Table mappings
                        </Link>
                    </li>
                    <li className="nav-item">
                        <a className="nav-link" href="https://discord.gg/xB9sR3Q7r3">
                            Support chat
                        </a>
                    </li>
                    <li className="nav-item">
                        <a className="nav-link" href="https://github.com/dickreuter/Poker">
                            Source code
                        </a>
                    </li>
                    <li className="nav-item">
                        <a
                            className="nav-link"
                            href="https://github.com/dickreuter/Poker/blob/master/readme.rst"
                        >
                            Documentation
                        </a>
                    </li>
                    <li className="nav-item">
                        <a className="nav-link" href="http://www.betfair-bot.com">
                            Betfair Bot
                        </a>
                    </li>
                </ul>
            </div>
        </nav>
    );
}

export default NavBar;
