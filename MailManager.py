import smtplib
from email.mime.text import MIMEText


class Mail:
    def __init__(self, subject, body, recipients):
        self.subject = subject
        self.html_body = body
        self.recipient = recipients
        self.sender = 'stopify5169@gmail.com'
        self.PASSWORD = 'nrhl ynkg nwmc yins'

    def send(self):
        msg = MIMEText(self.html_body, 'html')
        msg['Subject'] = self.subject
        msg['From'] = self.sender
        msg['To'] = ', '.join(self.recipient)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
            smtp_server.login(self.sender, self.PASSWORD)
            smtp_server.sendmail(self.sender, self.recipient, msg.as_string())
        print("Message sent!")


if __name__ == "__main__":
    mmail = Mail('omer', 'swimmer', 'uvlevy100@gmail.com')
    mmail.send()
