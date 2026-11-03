import ipaddress

from django.db import transaction
from django.utils import timezone

from .models import RegistrationPolicy, RegistrationPolicyAcceptance


def current_registration_policies(registration_session):
    """Return the current active policy versions that apply to this registration."""
    selected_class_ids = set(
        registration_session.selected_classes.values_list("pk", flat=True)
    )
    account_mode = str(
        (registration_session.account_data or {}).get("account_mode") or "new"
    ).strip().lower()

    policies = list(
        RegistrationPolicy.objects.filter(
            studio=registration_session.studio,
            is_current=True,
            is_active=True,
        )
        .prefetch_related("classes")
        .order_by("display_order", "title", "pk")
    )

    applicable = []
    for policy in policies:
        if policy.effective_date and policy.effective_date > timezone.localdate():
            continue

        if policy.scope == RegistrationPolicy.Scope.ACCOUNT:
            if account_mode == "existing":
                continue
            applicable.append(policy)
            continue

        if policy.scope == RegistrationPolicy.Scope.ALL_REGISTRATIONS:
            applicable.append(policy)
            continue

        if policy.scope == RegistrationPolicy.Scope.SPECIFIC_CLASSES:
            policy_class_ids = {class_instance.pk for class_instance in policy.classes.all()}
            if policy_class_ids & selected_class_ids:
                applicable.append(policy)

    return applicable


def policy_rows_for_registration(registration_session):
    existing_acceptances = {
        acceptance.policy_id: acceptance
        for acceptance in RegistrationPolicyAcceptance.objects.filter(
            registration_session=registration_session,
        )
    }

    rows = []
    selected_class_ids = set(
        registration_session.selected_classes.values_list("pk", flat=True)
    )
    for policy in current_registration_policies(registration_session):
        class_names = []
        if policy.scope == RegistrationPolicy.Scope.SPECIFIC_CLASSES:
            class_names = [
                class_instance.name
                for class_instance in policy.classes.all()
                if class_instance.pk in selected_class_ids
            ]
        rows.append({
            "policy": policy,
            "accepted": policy.pk in existing_acceptances,
            "acceptance": existing_acceptances.get(policy.pk),
            "class_names": class_names,
        })
    return rows


def registration_policies_satisfied(registration_session):
    selected_class_ids = sorted(
        registration_session.selected_classes.values_list("pk", flat=True)
    )
    account_mode = str(
        (registration_session.account_data or {}).get("account_mode") or "new"
    ).strip().lower()
    snapshot = registration_session.policy_snapshot or {}

    snapshot_class_ids = sorted(
        int(value)
        for value in snapshot.get("selected_class_ids", [])
        if str(value).isdigit()
    )
    snapshot_account_mode = str(snapshot.get("account_mode") or "").strip().lower()
    snapshot_policy_ids = {
        int(value)
        for value in snapshot.get("policy_ids", [])
        if str(value).isdigit()
    }

    if (
        snapshot.get("locked")
        and snapshot_class_ids == selected_class_ids
        and snapshot_account_mode == account_mode
    ):
        required_ids = snapshot_policy_ids
    else:
        required_ids = {policy.pk for policy in current_registration_policies(registration_session)}

    if not required_ids:
        return True

    accepted_ids = set(
        RegistrationPolicyAcceptance.objects.filter(
            registration_session=registration_session,
            policy_id__in=required_ids,
        ).values_list("policy_id", flat=True)
    )
    return required_ids.issubset(accepted_ids)


def missing_required_policies(registration_session):
    policies = current_registration_policies(registration_session)
    accepted_ids = set(
        RegistrationPolicyAcceptance.objects.filter(
            registration_session=registration_session,
        ).values_list("policy_id", flat=True)
    )
    return [
        policy
        for policy in policies
        if policy.pk not in accepted_ids
    ]


@transaction.atomic
def record_registration_policy_acceptances(
    registration_session,
    *,
    request,
    accepted_policy_ids,
    signatures=None,
):
    signatures = signatures or {}
    applicable = current_registration_policies(registration_session)
    applicable_by_id = {policy.pk: policy for policy in applicable}
    selected_class_ids = list(
        registration_session.selected_classes.values_list("pk", flat=True)
    )

    required_ids = {policy.pk for policy in applicable}
    accepted_ids = {
        int(value)
        for value in accepted_policy_ids
        if str(value).isdigit() and int(value) in applicable_by_id
    }

    missing_ids = required_ids - accepted_ids
    if missing_ids:
        missing = [applicable_by_id[pk].title for pk in sorted(missing_ids)]
        raise ValueError(
            "Please accept every required policy before continuing: "
            + ", ".join(missing)
        )

    signer_email = registration_session.contact_email or str(
        (registration_session.account_data or {}).get("email") or ""
    )
    account_data = registration_session.account_data or {}
    signer_name = " ".join(
        part.strip()
        for part in [
            str(account_data.get("guardian_first_name") or account_data.get("first_name") or ""),
            str(account_data.get("guardian_last_name") or account_data.get("last_name") or ""),
        ]
        if part and str(part).strip()
    ).strip()

    ip_address = None
    user_agent = ""
    if request is not None:
        forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        candidate_ip = forwarded or str(request.META.get("REMOTE_ADDR") or "").strip()
        try:
            ip_address = str(ipaddress.ip_address(candidate_ip)) if candidate_ip else None
        except ValueError:
            ip_address = None
        user_agent = str(request.META.get("HTTP_USER_AGENT") or "")[:1000]

    created = []
    for policy_id in sorted(accepted_ids):
        policy = applicable_by_id[policy_id]
        existing = RegistrationPolicyAcceptance.objects.filter(
            registration_session=registration_session,
            policy=policy,
        ).first()
        signature_value = str(signatures.get(str(policy_id)) or "").strip()
        if not signature_value and existing is not None:
            signature_value = existing.typed_signature
        if policy.requires_signature and not signature_value:
            raise ValueError(
                f"Type your full legal name for {policy.title} before continuing."
            )

        acceptance, _created = RegistrationPolicyAcceptance.objects.get_or_create(
            registration_session=registration_session,
            policy=policy,
            defaults={
                "policy_key": policy.policy_key,
                "policy_version": policy.version,
                "title_snapshot": policy.title,
                "document_type_snapshot": policy.document_type,
                "content_html_snapshot": policy.content_html,
                "acceptance_text_snapshot": policy.acceptance_label,
                "is_required_snapshot": True,
                "requires_signature_snapshot": policy.requires_signature,
                "typed_signature": signature_value,
                "signer_name": signer_name,
                "signer_email": signer_email,
                "selected_class_ids_snapshot": selected_class_ids,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "accepted_at": timezone.now(),
            },
        )
        created.append(acceptance)

    registration_session.policy_snapshot = {
        "locked": True,
        "policy_ids": sorted(applicable_by_id.keys()),
        "selected_class_ids": sorted(selected_class_ids),
        "account_mode": str(
            (registration_session.account_data or {}).get("account_mode") or "new"
        ).strip().lower(),
        "accepted_at": timezone.now().isoformat(),
    }
    registration_session.save(
        update_fields=["policy_snapshot", "updated_at"]
    )

    return created


def link_policy_acceptances_to_completed_registration(registration_session, *, user, family):
    RegistrationPolicyAcceptance.objects.filter(
        registration_session=registration_session,
    ).update(
        linked_user=user,
        linked_family=family,
    )
