import deathbycaptcha

'''
If a captcha pops up this class automatically sends a picture to deathbycaptcha and sends the necessary
commands to Virtualbox to enter the solved captcha
'''


def solveCaptcha(filename):
    # Put your DBC account username and password here.
    # Use deathbycaptcha.HttpClient for HTTP API.
    client = deathbycaptcha.SocketClient('dickreuter', 'wuschel')

    balance = client.get_balance()
    print("Death by Captcha Balance:")
    print(balance)

    # Put your CAPTCHA file name or file-like object, and optional
    # solving timeout (in seconds) here:
    captcha = client.decode(filename, 60)
    if captcha:
        print("CAPTCHA %s solved: %s" % (captcha["captcha"], captcha["text"]))
        return captcha["text"]

        # report incorrectly solved captcha:
        # client.report(captcha["captcha"])
        # except deathbycaptcha.AccessDeniedException:
        # Access to DBC API denied, check your credentials and/or balance
        #   print ("error")


if __name__ == '__main__':
    filename = "c:/temp/cpp2.png"
    result = solveCaptcha(filename)
    print(result)
