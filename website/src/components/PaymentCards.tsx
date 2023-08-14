import CloudDownloadOutlinedIcon from '@mui/icons-material/CloudDownloadOutlined';
import 'bootstrap/dist/css/bootstrap.css';
import Button from '@mui/material/Button';

function PaymentCards() {
    const dl_link = "https://onedrive.live.com/download?cid=A3B69BDCC03E82A9&resid=A3B69BDCC03E82A9%21111289&authkey=AEftpEpz8jxnBdI"

    const goToLink = (link: string) => {
        window.location.href = link;
    }
    return (
        <><br />
            <div className="container">
                <div className="row">
                    <div className="col-sm">
                        {/* <div className="shadow-lg p-0 mb-2 bg-white rounded"> */}
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Free</div>
                                <div> Trial </div>
                                <div><Button onClick={() => goToLink(dl_link)}
                                    variant="contained">Download</Button>
                                </div>
                                <div className="items">
                                    <ul><br />
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>
                                    </ul>
                                </div>
                            </div>
                            {/* </div> */}
                        </div>
                    </div>
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Monthly</div>
                                <div> $25 / month </div>
                                <div><Button onClick={() => goToLink('https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-910576034F790373KMC6UZOQ')}
                                    variant="contained">Subscribe</Button>
                                </div>
                                <div className="items">
                                    <ul><br />
                                        <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>

                                        <li>Support chat</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                    </ul>
                                </div>
                            </div>
                            {/* </div> */}
                        </div>
                    </div>
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Yearly</div>
                                <div> $49 / year </div>
                                <div>
                                    <Button onClick={() => goToLink('https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-6LY92142E3713805RMTML6SA')}
                                        variant="contained">Subscribe</Button>
                                </div>
                                <div className="items">
                                    <ul><br />
                                    <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>

                                        <li>Support chat</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="col-sm">
                        <div className="card shadow-lg rounded custom-card-size">
                            <div className="card-body">
                                <div> Lifetime</div>
                                <div> $99 / life </div>
                                <div>
                                    <Button onClick={() => goToLink('https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=PQX6RA3CEEED6')}
                                        variant="contained">Buy</Button>
                                </div>
                                <div className="items">
                                    <ul><br />
                                    <li>Scrape Table and Analyze</li>
                                        <li>Auto Click on best action</li>
                                        <li>Select table templates</li>
                                        <li>Map your own tables</li>
                                        <li>Analyze results</li>
                                        <li>Track payoff</li>

                                        <li>Support chat</li>
                                        <li>Edit strategies</li>
                                        <li>Create custom strategies</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    )
}

export default PaymentCards