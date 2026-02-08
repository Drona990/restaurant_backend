
from django.template.loader import render_to_string
from django.core.mail import EmailMessage

def send_otp_email(email, otp):
    html = render_to_string("otp_email.html", {"otp": otp})
    msg = EmailMessage("Your OTP Code", html, to=[email])
    msg.content_subtype = "html"
    msg.send()
