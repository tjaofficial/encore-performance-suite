from studios.models import Studio


def studio_branding(request):
    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    if not studio_slug:
        return {}

    studio = (
        Studio.objects
        .filter(
            slug=studio_slug,
            is_active=True,
        )
        .select_related("settings")
        .first()
    )

    if studio is None:
        return {}

    settings_obj = getattr(
        studio,
        "settings",
        None,
    )

    if settings_obj is None:
        return {
            "encore_branding_studio": studio,
            "encore_brand_primary": "#1663FF",
            "encore_brand_accent": "#0197FC",
            "encore_brand_logo": None,
        }

    return {
        "encore_branding_studio": studio,
        "encore_brand_primary": (
            settings_obj.primary_color
            or "#1663FF"
        ),
        "encore_brand_accent": (
            settings_obj.accent_color
            or "#0197FC"
        ),
        "encore_brand_logo": (
            settings_obj.logo
            if getattr(
                settings_obj,
                "logo",
                None,
            )
            else None
        ),
    }


def public_studio_branding(request):
    """
    Public pages do not always have a selected workspace in session,
    so this processor intentionally does nothing for public URLs.
    Public registration templates receive the studio object directly
    and resolve branding from studio.settings there.
    """
    return {}
