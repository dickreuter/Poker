import 'bootstrap/dist/css/bootstrap.css';
import PaymentCards from './Purchase';

function Home() {

    return (
        <>
            <div className="description">
                <div className="h4">Features</div>
                This pokerbot plays automatically on Pokerstars, Partypoker and GG Poker. Any other table can be mapped as well. It works with image recognition, montecarlo simulation and a basic genetic algorithm. The mouse is moved automatically and the bot can potentially play for hours based on a large number of parameters.
            </div>
            {/* <div className="titleimage">
                <img src="https://github.com/dickreuter/Poker/blob/e53d795e563abdc3e32656306ac46d1dcffc8816/doc/partypoker.gif?raw=true" style={{ transform: 'scale(1)' }} />
            </div> */}
            <div>
            <iframe src="https://app.colossyan.com/embed/a9de627b-0752-49c2-b9a6-dbc8dbf6e0f1" width="560" height="315" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
            {/* <iframe width="850" height="470" src="https://www.youtube.com/embed/EOqDSSeBXmQ?si=mNoG1KZMOmhlHQ7a" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe> */}
            </div>
            {/* <div className="pirateimage">
                <img src={pirate} height="200px" width="200px" />
            </div> */}
            <div className="download">
            </div>
            <PaymentCards />
        </>
    )
}

export default Home