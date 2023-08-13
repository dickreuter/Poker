import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import PaymentCards from './PaymentCards';

function Home() {
    const dl_link = "https://onedrive.live.com/download?cid=A3B69BDCC03E82A9&resid=A3B69BDCC03E82A9%21111289&authkey=AEftpEpz8jxnBdI"
    return (
        <>
            <div className="titleimage">
                <img src="https://github.com/dickreuter/Poker/blob/e53d795e563abdc3e32656306ac46d1dcffc8816/doc/partypoker.gif?raw=true" style={{ transform: 'scale(1)' }} />
            </div>
            <div className="download">
            </div>
            <PaymentCards />
        </>
    )
}

export default Home