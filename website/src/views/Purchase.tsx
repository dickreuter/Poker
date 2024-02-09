import Button from "@mui/material/Button";
import ClickAwayListener from "@mui/material/ClickAwayListener";
import Tooltip from "@mui/material/Tooltip";
import axios from "axios";
import "bootstrap/dist/css/bootstrap.css";
import { useState } from "react";
import { useDlLink } from './config';
import ReactGA from 'react-ga4'; // Import ReactGA

function PaymentCards() {
    const [hover, setHover] = useState(false);
    const [showBitcoin, setShowBitcoin] = useState(false);
    const bitcoinAddress = "bc1q6r0l549jefv3rgs7e0jzsdkx9pq9trd2cqyw50";
    const dlLink = useDlLink();
    const handleGAEvent = (action, label) => {
        // Track event with ReactGA
        ReactGA.event({
            category: 'Payment Option',
            action: action,
            label: label,
        });
    };
    const goToLink = (link, paymentType) => {
        handleGAEvent('Click', paymentType); // Track which payment option was clicked
        window.location.href = link;
    };

    const handleCopy = () => {
        handleGAEvent('Click', 'Bitcoin Address Copied'); // Track bitcoin copy event
        setShowBitcoin(!showBitcoin);
    };

    return (
        <>
            <br/>
            <div className="container">
                <div className="row">
                    {/* Free Version Card */}
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Free</div>
                                <div> Version</div>
                                <div>
                                    <Button onClick={() => goToLink(dlLink, 'Free Version')} variant="contained">
                                        Download
                                    </Button>
                                </div>
                                <div className="items">
                                    <ul>
                                        <br/>
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                        <br/>
                                        <li>Trial strategies</li>
                                        <br/>
                                        <li>Get free trial for betfair-bot.com</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Monthly Subscription Card */}
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Monthly</div>
                                <div> $25 / month</div>
                                <div>
                                    <Button
                                        onClick={() => goToLink("https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-910576034F790373KMC6UZOQ", 'Monthly Subscription')}
                                        variant="contained"
                                    >
                                        Subscribe
                                    </Button>
                                </div>
                                <div className="items">
                                    <ul>
                                        <br/>
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                        <br/>

                                        <li>Support chat</li>
                                        <li>Access to all strategies</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                        <br/>
                                        <li>Get free licence for betfair-bot.com</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Yearly Subscription Card */}
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> 1 year</div>
                                <div> $49 / year</div>
                                <div>
                                    <Button
                                        onClick={() => goToLink("https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=YZUR8CYZB826S", 'Yearly Subscription')}
                                        variant="contained"
                                    >
                                        Buy
                                    </Button>
                                </div>
                                <div className="items">
                                    <ul>
                                        <br/>
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                        <br/>

                                        <li>Support chat</li>
                                        <li>Access to all strategies</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                        <br/>
                                        <li>Get free licence for betfair-bot.com</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Bitcoin Payment Card */}
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Bitcoin</div>
                                <div>
                                    <ClickAwayListener onClickAway={() => setHover(false)}>
                                        <Tooltip title="Copy to Clipboard" open={hover} disableFocusListener
                                                 disableTouchListener>
                                            <Button
                                                onMouseEnter={() => setHover(true)}
                                                onMouseLeave={() => setHover(false)}
                                                onClick={handleCopy}
                                                variant="contained"
                                            >
                                                Bitcoin
                                            </Button>
                                        </Tooltip>
                                    </ClickAwayListener>
                                    {showBitcoin && (
                                        <div className="small">
                                            Bitcoin address: {bitcoinAddress} <br/>
                                            Please email me to confirm once you have made a payment: email@example.com
                                        </div>
                                    )}
                                </div>
                                <div className="items">
                                    <ul>
                                        <br/>
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                        <br/>

                                        <li>Support chat</li>
                                        <li>Access to all strategies</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                        <br/>
                                        <li>Get free licence for betfair-bot.com</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Lifetime Subscription Card */}
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Lifetime</div>
                                <div> $499 / life</div>
                                <div>
                                    <Button
                                        onClick={() => goToLink("https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=UNIQUEID", 'Lifetime Subscription')}
                                        variant="contained"
                                    >
                                        Buy
                                    </Button>
                                </div>
                                <div className="items">
                                    <ul>
                                        <br/>
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                        <br/>
                                        <li>Support chat</li>
                                        <li>Access to all strategies</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                        <br/>
                                        <li>Get free licence for betfair-bot.com</li>
                                        <br/>
                                        <li>Priority support</li>
                                        <br/>
                                        <li>Early access to new features</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
};


export default PaymentCards;