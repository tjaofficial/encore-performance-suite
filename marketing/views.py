from django.conf import settings
from django.shortcuts import render
from django.utils.html import escape

from communications.email_service import (
    EncoreEmailError,
    send_email,
)

from .contact_spam import (
    classify_contact_submission,
    create_contact_form_token,
)
from .forms import PublicContactForm


def home(request):
    return render(
        request,
        "marketing/home.html",
    )


def features(request):
    return render(
        request,
        "marketing/features.html",
    )


def pricing(request):
    return render(
        request,
        "marketing/pricing.html",
    )


def contact(request):
    sent = False
    send_error = ""

    if request.method == "POST":
        form = PublicContactForm(
            request.POST,
        )

        form_token = request.POST.get(
            "contact_form_token",
            "",
        )

        if form.is_valid():
            spam_result = classify_contact_submission(
                request,
                cleaned_data=form.cleaned_data,
                form_token=form_token,
            )

            if spam_result.is_spam:
                # Intentionally return the same success state for spam so
                # automated senders do not learn which protection fired.
                sent = True
                form = PublicContactForm()
            else:
                name = form.cleaned_data["name"]
                studio_name = form.cleaned_data["studio_name"]
                visitor_email = form.cleaned_data["email"]
                phone = form.cleaned_data["phone"]
                reason = form.reason_label
                message = form.cleaned_data["message"]

                safe_name = escape(name)
                safe_studio = escape(
                    studio_name or "Not provided"
                )
                safe_email = escape(visitor_email)
                safe_phone = escape(
                    phone or "Not provided"
                )
                safe_reason = escape(reason)
                safe_message = escape(
                    message
                ).replace(
                    "\n",
                    "<br>",
                )

                html_body = f"""
                    <div style="font-family:Arial,sans-serif;line-height:1.6;">
                        <h2>New Encore Contact Request</h2>
                        <p><strong>Reason:</strong> {safe_reason}</p>
                        <p><strong>Name:</strong> {safe_name}</p>
                        <p><strong>Studio:</strong> {safe_studio}</p>
                        <p><strong>Email:</strong> {safe_email}</p>
                        <p><strong>Phone:</strong> {safe_phone}</p>
                        <hr>
                        <p><strong>Message</strong></p>
                        <p>{safe_message}</p>
                    </div>
                """

                text_body = (
                    "New Encore Contact Request\n\n"
                    f"Reason: {reason}\n"
                    f"Name: {name}\n"
                    f"Studio: {studio_name or 'Not provided'}\n"
                    f"Email: {visitor_email}\n"
                    f"Phone: {phone or 'Not provided'}\n\n"
                    f"Message:\n{message}\n"
                )

                recipient = (
                    getattr(
                        settings,
                        "EMAIL_REPLY_TO",
                        "",
                    )
                    or "info@encoreperformancesuite.com"
                )

                try:
                    send_email(
                        to=[recipient],
                        subject=(
                            f"Encore Contact: {reason} — {name}"
                        ),
                        html_body=html_body,
                        text_body=text_body,
                        reply_to=[visitor_email],
                        tags={
                            "message_type": "public_contact",
                            "contact_reason": (
                                form.cleaned_data["reason"]
                            ),
                        },
                    )
                except EncoreEmailError:
                    send_error = (
                        "Encore could not send your message right now. "
                        "Please try again in a few minutes."
                    )
                else:
                    sent = True
                    form = PublicContactForm()
        else:
            form_token = create_contact_form_token()
    else:
        form = PublicContactForm()
        form_token = create_contact_form_token()

    if request.method == "POST" and sent:
        form_token = create_contact_form_token()

    return render(
        request,
        "marketing/contact.html",
        {
            "form": form,
            "contact_form_token": form_token,
            "contact_sent": sent,
            "contact_send_error": send_error,
        },
    )



def faq(request):
    return render(
        request,
        "marketing/faq.html",
    )
