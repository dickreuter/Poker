import 'bootstrap/dist/css/bootstrap.css';
import PaymentCards from './PaymentCards';

function Home() {

    return (
        <>
            <div className="description">
                <div className="h4">Features</div>
                This pokerbot plays automatically on Pokerstars, Partypoker and GG Poker. Any other table can be mapped as well. It works with image recognition, montecarlo simulation and a basic genetic algorithm. The mouse is moved automatically and the bot can potentially play for hours based on a large number of parameters.
            </div>
            <div className="titleimage">
                <img src="https://github.com/dickreuter/Poker/blob/e53d795e563abdc3e32656306ac46d1dcffc8816/doc/partypoker.gif?raw=true" style={{ transform: 'scale(1)' }} />
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