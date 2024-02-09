import React, { useState } from 'react';
import 'bootstrap/dist/css/bootstrap.css';
import { Link } from 'react-router-dom';
import { useDlLink } from '../views/config';
import ReactGA from 'react-ga4';

function NavBar() {
  const [isOpen, setIsOpen] = useState(false);
  const dlLink = useDlLink(); // Assume this hook provides a dynamic download link

  const toggle = () => {
    setIsOpen(!isOpen);
  };

  const handleGAEvent = (category, action, label) => {
    ReactGA.event({
      category: category,
      action: action,
      label: label,
    });
  };

  // Enhanced function to handle click events for both React Router Link and regular anchor tags
  const handleNavLinkClick = (label) => {
    if (window.innerWidth <= 768) {
      toggle();
    }
    handleGAEvent('Navigation', 'Link Click', label);
  };

  return (
    <nav className="navbar navbar-expand-sm fixed-top navbar-light bg-light">
      <button
        className="navbar-toggler"
        type="button"
        onClick={() => handleNavLinkClick('Navbar Toggle')}
        aria-label="Toggle navigation"
      >
        <span className="navbar-toggler-icon"></span>
      </button>
      <a className="navbar-brand" href="/" onClick={() => handleNavLinkClick('DeeperMind PokerBot')}>
        DeeperMind PokerBot
      </a>

      <div className={`collapse navbar-collapse ${isOpen ? 'show' : ''}`} id="navbarTogglerDemo03">
        <ul className="navbar-nav mr-auto">
          <li className="nav-item">
            <a className="nav-link" href={dlLink} onClick={() => handleNavLinkClick('Download')}>
              Download
            </a>
          </li>
          <li className="nav-item">
            <Link className="nav-link" to="/purchase" onClick={() => handleNavLinkClick('Purchase')}>
              Purchase
            </Link>
          </li>
          <li className="nav-item">
            <Link className="nav-link" to="/strategyanalyzer" onClick={() => handleNavLinkClick('Strategies')}>
              Strategies
            </Link>
          </li>
          <li className="nav-item">
            <Link className="nav-link" to="/tableanalyzer" onClick={() => handleNavLinkClick('Table Mappings')}>
              Table mappings
            </Link>
          </li>
          <li className="nav-item">
            <a className="nav-link" href="https://discord.gg/xB9sR3Q7r3" onClick={() => handleNavLinkClick('Support Chat')}>
              Support chat
            </a>
          </li>
          <li className="nav-item">
            <a className="nav-link" href="https://github.com/dickreuter/Poker" onClick={() => handleNavLinkClick('Source Code')}>
              Source code
            </a>
          </li>
          <li className="nav-item">
            <a
              className="nav-link"
              href="https://github.com/dickreuter/Poker/blob/master/readme.rst"
              onClick={() => handleNavLinkClick('Documentation')}
            >
              Documentation
            </a>
          </li>
          <li className="nav-item">
            <a className="nav-link" href="http://www.betfair-bot.com" onClick={() => handleNavLinkClick('Betfair Bot')}>
              Betfair Bot
            </a>
          </li>
        </ul>
      </div>
    </nav>
  );
}

export default NavBar;
